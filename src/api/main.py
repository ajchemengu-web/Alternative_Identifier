import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import numpy as np
import cv2
import sqlite3
from datetime import datetime, timedelta
from src.db import get_connection as _get_raw_connection
from src.services.recognition_service import recognize_image
from src.services.access_service import process_access
from src.services.guard_service import (
    get_pending_unknowns,
    admit_unknown_person,
    reject_unknown_person
)
from src.services import auth_service
from src.services.enrollment_service import enroll_student_face
from src.services import timetable_service
from src.services import unit_service
from src.services import dean_service
from src.services import camera_service
from src.services import me_service
from src.services import lecturer_service
from src.services import analytics_service
from src.services import retention_service
from src.services import watchlist_service
from src.services import investigation_service
from src.services import scene_service
from src.services import alerts_service
from src.api.deps import require_admin_tier, require_roles


# ==========================================
# DATA RETENTION SWEEP (docs/PRD.md §9)
# ==========================================
#
# Runs purge_expired_guests() on a timer for the lifetime of the
# process, so an admitted guest's facial data is actually deleted
# ~24 hours after admission rather than only being denied at
# recognition time. POST /admin/retention/sweep (below) covers the
# same ground on demand — useful for an operator, a test, or an
# external cron hitting a deployment where this in-process loop
# isn't relied on.

RETENTION_SWEEP_INTERVAL_SECONDS = 3600


async def _retention_sweep_loop():

    while True:

        try:

            retention_service.purge_expired_guests()

        except Exception as error:

            print(f"[retention] sweep failed: {error}")

        await asyncio.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):

    task = asyncio.create_task(_retention_sweep_loop())

    yield

    task.cancel()


app = FastAPI(
    title="Smart Hostel Security API",
    description="AI-powered hostel access management system",
    version="1.0.0",
    lifespan=lifespan
)


# smart-gen.com (Next.js) never hits this from the browser — every
# call there is server-side (src/lib/api.ts), invisible to CORS. The
# SmartAttendance Flutter app running as *web* is the one caller that
# does call this API directly from a browser, from whatever localhost
# port `flutter run -d chrome` picks each time — so this is permissive
# by necessity, not by accident. Safe regardless: nothing here relies
# on cookies (auth is a Bearer access_token the client attaches
# itself), so there's no credentialed cross-origin session to leak.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():

    connection = _get_raw_connection()

    connection.row_factory = sqlite3.Row

    return connection


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():

    return {
        "message": "Welcome to Smart Hostel Security API",
        "system": "running"
    }


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "Smart Hostel Security API"
    }


# ==========================================
# GET STUDENTS
# ==========================================

@app.get("/students")
def get_students(
    department: Optional[str] = None,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    connection = get_connection()

    cursor = connection.cursor()

    if department:

        cursor.execute("""
            SELECT
                student_id,
                full_name,
                admission_number,
                hostel,
                room,
                department,
                course,
                year,
                semester,
                embedding_file
            FROM students
            WHERE department = ?
        """, (department,))

    else:

        cursor.execute("""
            SELECT
                student_id,
                full_name,
                admission_number,
                hostel,
                room,
                department,
                course,
                year,
                semester,
                embedding_file
            FROM students
        """)

    students = cursor.fetchall()

    connection.close()

    return [
        {
            **dict(student),
            "face_enrolled": student["embedding_file"] is not None
        }
        for student in students
    ]


# ==========================================
# REGISTER A STUDENT RECORD (docs/PRD.md §5)
# ==========================================
#
# Creates the record only — no embedding yet. Distinct from
# POST /enroll/student-face below, which requires an existing record
# (created here) and attaches a photo-derived embedding to it,
# either by an admin (that endpoint) or by the student themselves
# (POST /me/enroll-face).

class StudentRecordRequest(BaseModel):

    student_id: str
    full_name: str
    admission_number: str
    hostel: str
    room: str
    department: Optional[str] = None
    course: Optional[str] = None
    year: Optional[int] = None
    semester: Optional[int] = None


@app.post("/students")
def create_student(
    request: StudentRecordRequest,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    try:

        result = enrollment_service.create_student_record(
            student_id=request.student_id,
            full_name=request.full_name,
            admission_number=request.admission_number,
            hostel=request.hostel,
            room=request.room,
            department=request.department,
            course=request.course,
            year=request.year,
            semester=request.semester
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    return result


# ==========================================
# GET GUESTS
# ==========================================

@app.get("/guests")
def get_guests(current_user: dict = Depends(require_roles("ADMIN"))):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            guest_id,
            status,
            admitted_by,
            admitted_at,
            expires_at
        FROM guests
        ORDER BY expires_at DESC
    """)

    guests = cursor.fetchall()

    connection.close()

    return [
        dict(guest)
        for guest in guests
    ]


# ==========================================
# GET ACCESS LOGS
# ==========================================

@app.get("/access-logs")
def get_access_logs(
    current_user: dict = Depends(require_roles("ADMIN", "GUARD"))
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            person_type,
            person_identifier,
            entrance,
            recognition_score,
            liveness_score,
            decision,
            guard_id,
            false_positive,
            false_positive_reason,
            timestamp
        FROM access_logs
        ORDER BY timestamp DESC
        LIMIT 100
    """)

    logs = cursor.fetchall()

    connection.close()

    return [
        dict(log)
        for log in logs
    ]


# ==========================================
# FALSE-POSITIVE FLAGGING + ANALYTICS
# (docs/PRD.md §13 Phase 3)
# ==========================================
#
# There's no ground truth to infer a false positive from
# automatically — see analytics_service.py's docstring. A Guard or
# Admin flags one after determining, outside this system, that a
# VERIFIED entry actually matched the wrong person.

class FalsePositiveRequest(BaseModel):

    reason: str


@app.patch("/access-logs/{access_log_id}/false-positive")
def flag_access_log_false_positive(
    access_log_id: int,
    request: FalsePositiveRequest,
    current_user: dict = Depends(require_roles("ADMIN", "GUARD"))
):

    updated = analytics_service.flag_false_positive(
        access_log_id,
        request.reason,
        current_user["username"]
    )

    if not updated:

        raise HTTPException(
            status_code=404,
            detail="Access log entry not found"
        )

    return {"success": True}


@app.get("/analytics/summary")
def get_analytics_summary(
    since_days: Optional[int] = None,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    since = (
        datetime.now() - timedelta(days=since_days)
        if since_days is not None
        else None
    )

    return analytics_service.get_summary(since)


# ==========================================
# AI FACE RECOGNITION
# ==========================================

@app.post("/recognize")
async def recognize(
    file: UploadFile = File(...),
    camera_id: Optional[str] = Form(None),
    current_user: dict = Depends(require_roles("ADMIN", "GUARD"))
):

    # Check uploaded file type
    if not file.content_type.startswith("image/"):

        raise HTTPException(
            status_code=400,
            detail="Please upload an image file."
        )


    # Read image bytes
    image_bytes = await file.read()


    # Convert bytes into NumPy array
    image_array = np.frombuffer(
        image_bytes,
        np.uint8
    )


    # Decode image for OpenCV
    image = cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR
    )


    if image is None:

        raise HTTPException(
            status_code=400,
            detail="Could not decode image."
        )


    # ======================================
    # SEND IMAGE TO AI
    # ======================================

    recognition_result = recognize_image(image)

    # A guard checkpoint device may identify which registered camera
    # it's posting from; that camera's own location (docs/PRD.md §8's
    # camera registry) becomes the access_logs "entrance" for this
    # sighting, instead of the single hardcoded gate name — this is
    # what makes scene_service's location+time scene reconstruction
    # meaningful across more than one checkpoint. Falls back to the
    # default gate name if no camera_id is sent or it doesn't match a
    # registered camera.
    entrance = "Nyayo Main Gate"

    if camera_id:

        camera = camera_service.get_camera(camera_id)

        if camera and camera.get("location"):

            entrance = camera["location"]

    access_result = process_access(
        recognition_result,
        image,
        entrance=entrance
    )

    return access_result

@app.get("/guard/pending")

def get_pending_persons(
    current_user: dict = Depends(require_roles("ADMIN", "GUARD"))
):

    pending = get_pending_unknowns()

    return {

        "total_pending": len(pending),

        "unknown_persons": pending

    }

@app.post("/guard/admit/{unknown_id}")

def admit_person(
    unknown_id: str,
    current_user: dict = Depends(require_roles("ADMIN", "GUARD"))
):

    result = admit_unknown_person(
        unknown_id
    )

    return result

@app.post("/guard/reject/{unknown_id}")

def reject_person(
    unknown_id: str,
    current_user: dict = Depends(require_roles("ADMIN", "GUARD"))
):

    result = reject_unknown_person(
        unknown_id
    )

    return result


# ==========================================
# ENROLLMENT DASHBOARD (docs/PRD.md §5)
# ==========================================
#
# /login is intentionally the one open endpoint here — it's how a
# caller gets an access_token in the first place. Everything else
# below requires one, via src/api/deps.py.

class EnrollRequest(BaseModel):

    username: str
    password: str
    email: str
    role: str
    admin_tier: Optional[str] = None
    linked_person_id: Optional[str] = None
    location: Optional[str] = None


class LoginRequest(BaseModel):

    username: str
    password: str


@app.post("/enroll")
def enroll(
    request: EnrollRequest,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    try:

        result = auth_service.create_user(
            username=request.username,
            password=request.password,
            email=request.email,
            role=request.role,
            admin_tier=request.admin_tier,
            linked_person_id=request.linked_person_id,
            location=request.location
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception:

        raise HTTPException(
            status_code=400,
            detail=(
                "Could not create user — username or email "
                "may already be in use."
            )
        )

    return result


@app.post("/login")
def login(request: LoginRequest):

    result = auth_service.authenticate(
        request.username,
        request.password
    )

    if result is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    return result


@app.post("/admin/temporary-admins/{username}/complete")
def complete_temporary_admin_task(
    username: str,
    current_user: dict = Depends(require_admin_tier("ORIGINAL"))
):

    result = auth_service.mark_temporary_admin_task_complete(
        username
    )

    if not result["success"]:

        raise HTTPException(
            status_code=404,
            detail=result["message"]
        )

    return result


# ==========================================
# STUDENT FACIAL ENROLLMENT (docs/PRD.md §5)
# ==========================================
#
# Live counterpart to src/enroll_students.py (an interactive webcam
# CLI script, not reachable from this API). Takes one or more
# reference photos instead of a live multi-sample capture loop.
# STUDENT role only for now — see the scope note in
# src/services/enrollment_service.py.

@app.post("/enroll/student-face")
async def enroll_student_face_endpoint(
    student_id: str,
    full_name: str,
    admission_number: str,
    hostel: str,
    room: str,
    department: Optional[str] = None,
    course: Optional[str] = None,
    year: Optional[int] = None,
    semester: Optional[int] = None,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(require_roles("ADMIN"))
):

    images = []

    for file in files:

        if not file.content_type.startswith("image/"):

            raise HTTPException(
                status_code=400,
                detail=f"{file.filename} is not an image file."
            )

        image_bytes = await file.read()

        image_array = np.frombuffer(image_bytes, np.uint8)

        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if image is None:

            raise HTTPException(
                status_code=400,
                detail=f"Could not decode {file.filename}."
            )

        images.append(image)

    try:

        result = enroll_student_face(
            student_id=student_id,
            full_name=full_name,
            admission_number=admission_number,
            hostel=hostel,
            room=room,
            images=images,
            department=department,
            course=course,
            year=year,
            semester=semester
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    return result


# ==========================================
# UNITS (docs/PRD.md §6, §8)
# ==========================================
#
# The unit registry: the Timetabling Admin creates a unit once
# (unit_code/unit_name/department/course/year/semester); a lecturer
# then claims the units they teach from the app. A timetable entry
# references a unit_id instead of a facilitator name typed fresh
# each time (see unit_service.py's docstring and
# TimetableEntryRequest below).

class UnitRequest(BaseModel):

    unit_code: str
    unit_name: str
    course: str
    year: int
    semester: int
    department: Optional[str] = None


class UnitLecturerRequest(BaseModel):

    lecturer_id: Optional[str] = None


@app.get("/units")
def get_units(
    department: Optional[str] = None,
    course: Optional[str] = None,
    year: Optional[int] = None,
    semester: Optional[int] = None,
    lecturer_id: Optional[str] = None,
    unclaimed: Optional[bool] = None,
    current_user: dict = Depends(require_roles("ADMIN", "LECTURER"))
):

    return unit_service.list_units(
        department=department,
        course=course,
        year=year,
        semester=semester,
        lecturer_id=lecturer_id,
        unclaimed=unclaimed
    )


@app.post("/units")
def create_unit_endpoint(
    request: UnitRequest,
    current_user: dict = Depends(
        require_admin_tier("TIMETABLING", "ORIGINAL")
    )
):

    try:

        return unit_service.create_unit(
            unit_code=request.unit_code,
            unit_name=request.unit_name,
            course=request.course,
            year=request.year,
            semester=request.semester,
            department=request.department,
            created_by=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@app.patch("/units/{unit_id}/claim")
def claim_unit_endpoint(
    unit_id: int,
    current_user: dict = Depends(require_roles("LECTURER"))
):

    profile = me_service.get_my_lecturer_profile(current_user["username"])

    if profile is None:

        raise HTTPException(
            status_code=404,
            detail="No linked lecturer profile for this account"
        )

    try:

        return unit_service.claim_unit(unit_id, profile["lecturer_id"])

    except ValueError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error)
        )


@app.patch("/units/{unit_id}/unclaim")
def unclaim_unit_endpoint(
    unit_id: int,
    current_user: dict = Depends(require_roles("LECTURER"))
):

    profile = me_service.get_my_lecturer_profile(current_user["username"])

    if profile is None:

        raise HTTPException(
            status_code=404,
            detail="No linked lecturer profile for this account"
        )

    try:

        return unit_service.unclaim_unit(unit_id, profile["lecturer_id"])

    except ValueError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error)
        )


@app.patch("/units/{unit_id}/lecturer")
def set_unit_lecturer_endpoint(
    unit_id: int,
    request: UnitLecturerRequest,
    current_user: dict = Depends(
        require_admin_tier("TIMETABLING", "ORIGINAL")
    )
):

    try:

        return unit_service.set_unit_lecturer(unit_id, request.lecturer_id)

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


# ==========================================
# TIMETABLING (docs/PRD.md §8)
# ==========================================
#
# Any admin can view a timetable; only the Timetabling Admin (or the
# Original Admin, as the overall system owner) can create, postpone,
# cancel, or delete an entry.

class TimetableEntryRequest(BaseModel):

    # A unit already carries its own department/course/year/semester
    # and (once claimed) its lecturer — see unit_service.py's
    # docstring — so creating an entry only needs the unit plus
    # when/where it meets.
    unit_id: int
    day_of_week: str
    start_time: str
    end_time: str
    venue: str


class TimetableStatusRequest(BaseModel):

    status: str


@app.get("/timetable")
def get_timetable(
    course: Optional[str] = None,
    year: Optional[int] = None,
    department: Optional[str] = None,
    facilitator: Optional[str] = None,
    semester: Optional[int] = None,
    lecturer_id: Optional[str] = None,
    unit_id: Optional[int] = None,
    current_user: dict = Depends(require_roles("ADMIN", "STUDENT", "LECTURER"))
):

    return timetable_service.list_entries(
        course=course,
        year=year,
        department=department,
        facilitator=facilitator,
        semester=semester,
        lecturer_id=lecturer_id,
        unit_id=unit_id
    )


@app.post("/timetable")
def create_timetable_entry(
    request: TimetableEntryRequest,
    current_user: dict = Depends(
        require_admin_tier("TIMETABLING", "ORIGINAL")
    )
):

    try:

        return timetable_service.create_entry(
            unit_id=request.unit_id,
            day_of_week=request.day_of_week,
            start_time=request.start_time,
            end_time=request.end_time,
            venue=request.venue,
            created_by=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@app.patch("/timetable/{entry_id}/status")
def update_timetable_entry_status(
    entry_id: int,
    request: TimetableStatusRequest,
    current_user: dict = Depends(
        require_admin_tier("TIMETABLING", "ORIGINAL")
    )
):

    try:

        updated = timetable_service.update_status(
            entry_id,
            request.status
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    if not updated:

        raise HTTPException(
            status_code=404,
            detail="Timetable entry not found"
        )

    return {"success": True}


@app.delete("/timetable/{entry_id}")
def delete_timetable_entry(
    entry_id: int,
    current_user: dict = Depends(
        require_admin_tier("TIMETABLING", "ORIGINAL")
    )
):

    deleted = timetable_service.delete_entry(entry_id)

    if not deleted:

        raise HTTPException(
            status_code=404,
            detail="Timetable entry not found"
        )

    return {"success": True}


# ==========================================
# DEAN OF SCHOOL ADMIN (docs/PRD.md §8)
# ==========================================
#
# Roster + timetable/unit totals scoped to a department. "Class
# logs" and "venue camera access" (also part of this tier's PRD
# scope) need the classroom-camera pipeline and camera management,
# neither of which exist in this backend yet.

@app.get("/dean/roster")
def get_dean_roster(
    department: Optional[str] = None,
    current_user: dict = Depends(
        require_admin_tier("DEAN", "ORIGINAL")
    )
):

    return dean_service.get_roster(department)


@app.get("/dean/summary")
def get_dean_summary(
    department: Optional[str] = None,
    current_user: dict = Depends(
        require_admin_tier("DEAN", "ORIGINAL")
    )
):

    return dean_service.get_summary(department)


# ==========================================
# CAMERA MANAGEMENT (docs/PRD.md §8)
# ==========================================
#
# A persisted registry (src/services/camera_service.py) separate
# from the runtime CameraManager in src/camera/ that actually drives
# camera hardware for the live recognition pipeline — see that
# service's own module docstring for why. Any admin can view the
# registry (the Dean uses ?department= for "venue camera access"
# scoped to their school); only the Original Admin can provision or
# remove a camera; the Original and Security Admins can update a
# camera's configuration/status ("camera management control" and
# "camera access/configuration within SmartAccess" respectively).
#
# camera_type is which product this camera serves —
# CHECKPOINT = SmartAccess (a gate/checkpoint), CLASSROOM =
# SmartAttendance — see camera_service.CAMERA_TYPES. location and
# source (the IP camera's RTSP/HTTP stream address) are required at
# creation: a camera registered without either isn't meaningfully
# addable — the whole point of manually adding an IP camera here is
# recording where it is and how to reach it.

class CameraRequest(BaseModel):

    camera_id: str
    name: str
    camera_type: str
    location: str
    source: str
    department: Optional[str] = None


class CameraUpdateRequest(BaseModel):

    name: Optional[str] = None
    location: Optional[str] = None
    source: Optional[str] = None
    enabled: Optional[bool] = None


class CameraStatusRequest(BaseModel):

    status: str


@app.get("/cameras")
def get_cameras(
    camera_type: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    return camera_service.list_cameras(camera_type, department, status)


@app.post("/cameras")
def create_camera(
    request: CameraRequest,
    current_user: dict = Depends(
        require_admin_tier("ORIGINAL")
    )
):

    try:

        return camera_service.create_camera(
            camera_id=request.camera_id,
            name=request.name,
            camera_type=request.camera_type,
            location=request.location,
            department=request.department,
            source=request.source,
            created_by=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@app.patch("/cameras/{camera_id}")
def update_camera(
    camera_id: str,
    request: CameraUpdateRequest,
    current_user: dict = Depends(
        require_admin_tier("ORIGINAL", "SECURITY")
    )
):

    try:

        updated = camera_service.update_camera(
            camera_id,
            name=request.name,
            location=request.location,
            source=request.source,
            enabled=request.enabled
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    if not updated:

        raise HTTPException(
            status_code=404,
            detail="Camera not found"
        )

    return {"success": True}


@app.patch("/cameras/{camera_id}/status")
def update_camera_status(
    camera_id: str,
    request: CameraStatusRequest,
    current_user: dict = Depends(
        require_admin_tier("ORIGINAL", "SECURITY")
    )
):

    try:

        updated = camera_service.update_status(
            camera_id,
            request.status
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    if not updated:

        raise HTTPException(
            status_code=404,
            detail="Camera not found"
        )

    return {"success": True}


@app.delete("/cameras/{camera_id}")
def delete_camera(
    camera_id: str,
    current_user: dict = Depends(
        require_admin_tier("ORIGINAL")
    )
):

    deleted = camera_service.delete_camera(camera_id)

    if not deleted:

        raise HTTPException(
            status_code=404,
            detail="Camera not found"
        )

    return {"success": True}


# ==========================================
# SMARTATTENDANCE — "MY PROFILE" (docs/PRD.md
# §6, Phase 2)
# ==========================================
#
# Students/lecturers don't use the web dashboards (docs/PRD.md §4) —
# this is for the separate SmartAttendance app to resolve its own
# logged-in user to what it can request a timetable for (a
# student's course/year, or a lecturer's own name to match against
# timetable_entries.facilitator).

@app.get("/me")
def get_me(
    current_user: dict = Depends(require_roles("STUDENT", "LECTURER"))
):

    if current_user["role"] == "STUDENT":

        profile = me_service.get_my_student_profile(
            current_user["username"]
        )

        not_found_detail = "No linked student profile found for this account"

    else:

        profile = me_service.get_my_lecturer_profile(
            current_user["username"]
        )

        not_found_detail = "No linked lecturer profile found for this account"

    if profile is None:

        raise HTTPException(
            status_code=404,
            detail=not_found_detail
        )

    return {**profile, "role": current_user["role"]}


# ==========================================
# SELF-SERVICE FACIAL ENROLLMENT (docs/PRD.md §5)
# ==========================================
#
# A STUDENT enrolling their own face, from their own logged-in
# session — the SmartAttendance app's counterpart to the admin-run
# POST /enroll/student-face above. Requires the student's record to
# already exist (an admin creates it via POST /students; no
# self-registration, docs/PRD.md §9) and every candidate photo to
# pass the liveness check (enrollment_service.py's
# _live_embedding_from_image) — there's no admin present to catch a
# spoofed photo the way there is for admin-run enrollment.

@app.post("/me/enroll-face")
async def enroll_my_face_endpoint(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(require_roles("STUDENT"))
):

    images = []

    for file in files:

        if not file.content_type.startswith("image/"):

            raise HTTPException(
                status_code=400,
                detail=f"{file.filename} is not an image file."
            )

        image_bytes = await file.read()

        image_array = np.frombuffer(image_bytes, np.uint8)

        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if image is None:

            raise HTTPException(
                status_code=400,
                detail=f"Could not decode {file.filename}."
            )

        images.append(image)

    try:

        result = enrollment_service.enroll_own_face(
            current_user["username"],
            images
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    return result


# ==========================================
# LECTURER PROFILES (docs/PRD.md §5, §6)
# ==========================================
#
# A lecturer profile (full_name/department, no facial embedding —
# see lecturer_service.py's docstring) that an admin creates before
# enrolling that person's LECTURER login via POST /enroll,
# referencing this lecturer_id as linked_person_id. Lets
# SmartAttendance resolve a logged-in lecturer to their own units
# via GET /me + GET /timetable?facilitator=.

class LecturerRequest(BaseModel):

    lecturer_id: str
    full_name: str
    department: Optional[str] = None


@app.get("/lecturers")
def get_lecturers(
    department: Optional[str] = None,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    return lecturer_service.list_lecturers(department)


@app.post("/lecturers")
def create_lecturer(
    request: LecturerRequest,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    try:

        return lecturer_service.create_lecturer(
            lecturer_id=request.lecturer_id,
            full_name=request.full_name,
            department=request.department
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


# ==========================================
# DATA RETENTION (docs/PRD.md §9)
# ==========================================
#
# The lifespan-managed loop above already runs this on a timer;
# this lets an Original Admin (or an external cron against a real
# deployment) trigger the same sweep on demand.

@app.post("/admin/retention/sweep")
def run_retention_sweep(
    current_user: dict = Depends(
        require_admin_tier("ORIGINAL")
    )
):

    purged_guest_ids = retention_service.purge_expired_guests()

    return {
        "purged_guest_ids": purged_guest_ids,
        "count": len(purged_guest_ids)
    }


# ==========================================
# WATCHLIST / TARGET TRACKING (docs/PRD.md §8)
# ==========================================
#
# SmartAccess-specific: a dedicated dashboard for the Security Admin
# (or Original Admin, as overall owner) to register and track
# persons of interest, either with reference photos or — if already
# enrolled as a student — by admission_number, which reuses that
# student's own stored embedding (full_name is then derived from the
# student record too). A target with a stored embedding is checked
# by the live recognition pipeline ahead of students/guests — see
# watchlist_service.py and access_service.py's TARGET_MATCH branch.

@app.post("/watchlist")
async def create_watchlist_target(
    full_name: Optional[str] = None,
    description: Optional[str] = None,
    reason: Optional[str] = None,
    admission_number: Optional[str] = None,
    images: List[UploadFile] = File(default=[]),
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    decoded_images = []

    for file in images:

        if not file.content_type.startswith("image/"):

            raise HTTPException(
                status_code=400,
                detail=f"{file.filename} is not an image file."
            )

        image_bytes = await file.read()

        image_array = np.frombuffer(image_bytes, np.uint8)

        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if image is None:

            raise HTTPException(
                status_code=400,
                detail=f"Could not decode {file.filename}."
            )

        decoded_images.append(image)

    try:

        return watchlist_service.create_target(
            full_name=full_name,
            description=description,
            reason=reason,
            images=decoded_images,
            admission_number=admission_number,
            created_by=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@app.get("/watchlist")
def get_watchlist(
    status: Optional[str] = None,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    return watchlist_service.list_targets(status)


@app.get("/watchlist/{target_id}/sightings")
def get_watchlist_sightings(
    target_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    target = watchlist_service.get_target(target_id)

    if target is None:

        raise HTTPException(
            status_code=404,
            detail="Target not found"
        )

    return watchlist_service.get_sightings(target_id)


@app.get("/watchlist/{target_id}/frequency")
def get_watchlist_frequency(
    target_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    target = watchlist_service.get_target(target_id)

    if target is None:

        raise HTTPException(
            status_code=404,
            detail="Target not found"
        )

    return watchlist_service.get_sighting_frequency(target_id)


@app.patch("/watchlist/{target_id}/resolve")
def resolve_watchlist_target(
    target_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    resolved = watchlist_service.resolve_target(
        target_id,
        current_user["username"]
    )

    if not resolved:

        raise HTTPException(
            status_code=404,
            detail="Target not found"
        )

    return {"success": True}


@app.patch("/watchlist/{target_id}/reactivate")
def reactivate_watchlist_target(
    target_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    reactivated = watchlist_service.reactivate_target(target_id)

    if not reactivated:

        raise HTTPException(
            status_code=404,
            detail="Target not found"
        )

    return {"success": True}


# ==========================================
# INVESTIGATIONS (docs/PRD.md §8)
# ==========================================
#
# SmartAccess case management, same dashboard/role scope as the
# watchlist above — see investigation_service.py.

class InvestigationRequest(BaseModel):

    title: str
    description: Optional[str] = None
    target_id: Optional[str] = None
    severity: Optional[str] = "MEDIUM"
    assigned_to: Optional[str] = None


class InvestigationUpdateRequest(BaseModel):

    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    assigned_to: Optional[str] = None


class InvestigationNoteRequest(BaseModel):

    note: str


class LinkTargetRequest(BaseModel):

    target_id: str


class LinkUnknownRequest(BaseModel):

    unknown_id: str


@app.post("/investigations")
def create_investigation(
    request: InvestigationRequest,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    try:

        return investigation_service.create_case(
            title=request.title,
            description=request.description,
            target_id=request.target_id,
            severity=request.severity,
            assigned_to=request.assigned_to,
            opened_by=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@app.patch("/investigations/{case_id}")
def update_investigation(
    case_id: str,
    request: InvestigationUpdateRequest,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    try:

        return investigation_service.update_case(
            case_id,
            title=request.title,
            description=request.description,
            severity=request.severity,
            assigned_to=request.assigned_to
        )

    except ValueError as error:

        status_code = 404 if "case_id" in str(error) else 400

        raise HTTPException(
            status_code=status_code,
            detail=str(error)
        )


@app.get("/investigations")
def get_investigations(
    status: Optional[str] = None,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    return investigation_service.list_cases(status)


@app.get("/investigations/{case_id}")
def get_investigation(
    case_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    case = investigation_service.get_case(case_id)

    if case is None:

        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    return case


@app.post("/investigations/{case_id}/notes")
def add_investigation_note(
    case_id: str,
    request: InvestigationNoteRequest,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    try:

        return investigation_service.add_note(
            case_id,
            request.note,
            author=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error)
        )


@app.patch("/investigations/{case_id}/close")
def close_investigation(
    case_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    closed = investigation_service.close_case(
        case_id,
        current_user["username"]
    )

    if not closed:

        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    return {"success": True}


@app.patch("/investigations/{case_id}/reopen")
def reopen_investigation(
    case_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    reopened = investigation_service.reopen_case(case_id)

    if not reopened:

        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    return {"success": True}


@app.post("/investigations/{case_id}/targets")
def link_investigation_target(
    case_id: str,
    request: LinkTargetRequest,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    try:

        return investigation_service.link_target(
            case_id,
            request.target_id,
            linked_by=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error)
        )


@app.delete("/investigations/{case_id}/targets/{target_id}")
def unlink_investigation_target(
    case_id: str,
    target_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    unlinked = investigation_service.unlink_target(case_id, target_id)

    if not unlinked:

        raise HTTPException(
            status_code=404,
            detail="That target isn't linked to this case"
        )

    return {"success": True}


@app.post("/investigations/{case_id}/unknowns")
def link_investigation_unknown(
    case_id: str,
    request: LinkUnknownRequest,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    try:

        return investigation_service.link_unknown(
            case_id,
            request.unknown_id,
            linked_by=current_user["username"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error)
        )


@app.delete("/investigations/{case_id}/unknowns/{unknown_id}")
def unlink_investigation_unknown(
    case_id: str,
    unknown_id: str,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    unlinked = investigation_service.unlink_unknown(case_id, unknown_id)

    if not unlinked:

        raise HTTPException(
            status_code=404,
            detail="That unknown sighting isn't linked to this case"
        )

    return {"success": True}


# ==========================================
# SCENE RECONSTRUCTION (docs/PRD.md §8)
# ==========================================
#
# Same dashboard/role scope as watchlist/investigations above — pick
# a location (a scene) and a time window, see every face access_logs
# actually recognized there during it. See scene_service.py.

@app.get("/scene/locations")
def get_scene_locations(
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    return scene_service.list_locations()


@app.get("/scene/query")
def get_scene_query(
    location: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    co_occurrence_minutes: Optional[int] = None,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    return scene_service.query_scene(
        location=location,
        start_time=start_time,
        end_time=end_time,
        co_occurrence_minutes=co_occurrence_minutes
    )


# ==========================================
# TARGET ALERTS (docs/PRD.md §8)
# ==========================================
#
# Same dashboard/role scope as watchlist/investigations/scene above —
# every unacknowledged TARGET_ALERT access_logs row, for a dashboard
# to poll into a live-feeling alert banner. See alerts_service.py for
# why this is a poll queue rather than an outbound push/SMS/email.

@app.get("/alerts/pending")
def get_pending_alerts(
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    return alerts_service.list_pending_alerts()


@app.patch("/alerts/{access_log_id}/acknowledge")
def acknowledge_alert(
    access_log_id: int,
    current_user: dict = Depends(
        require_admin_tier("SECURITY", "ORIGINAL")
    )
):

    acknowledged = alerts_service.acknowledge_alert(
        access_log_id,
        current_user["username"]
    )

    if not acknowledged:

        raise HTTPException(
            status_code=404,
            detail="No pending alert with that id"
        )

    return {"success": True}
