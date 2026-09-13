from fastapi import Depends, FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import numpy as np
import cv2
import sqlite3
from datetime import datetime
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
from src.services import dean_service
from src.services import camera_service
from src.services import me_service
from src.api.deps import require_admin_tier, require_roles


app = FastAPI(
    title="Smart Hostel Security API",
    description="AI-powered hostel access management system",
    version="1.0.0"
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
                year
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
                year
            FROM students
        """)

    students = cursor.fetchall()

    connection.close()

    return [
        dict(student)
        for student in students
    ]


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
# AI FACE RECOGNITION
# ==========================================

@app.post("/recognize")
async def recognize(
    file: UploadFile = File(...),
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

    access_result = process_access(
    recognition_result,
    image
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
            linked_person_id=request.linked_person_id
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
            year=year
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    return result


# ==========================================
# TIMETABLING (docs/PRD.md §8)
# ==========================================
#
# Any admin can view a timetable; only the Timetabling Admin (or the
# Original Admin, as the overall system owner) can create, postpone,
# cancel, or delete an entry.

class TimetableEntryRequest(BaseModel):

    course: str
    year: int
    day_of_week: str
    start_time: str
    end_time: str
    unit_name: str
    facilitator: str
    venue: str
    department: Optional[str] = None


class TimetableStatusRequest(BaseModel):

    status: str


@app.get("/timetable")
def get_timetable(
    course: Optional[str] = None,
    year: Optional[int] = None,
    department: Optional[str] = None,
    current_user: dict = Depends(require_roles("ADMIN"))
):

    return timetable_service.list_entries(course, year, department)


@app.post("/timetable")
def create_timetable_entry(
    request: TimetableEntryRequest,
    current_user: dict = Depends(
        require_admin_tier("TIMETABLING", "ORIGINAL")
    )
):

    try:

        return timetable_service.create_entry(
            course=request.course,
            year=request.year,
            day_of_week=request.day_of_week,
            start_time=request.start_time,
            end_time=request.end_time,
            unit_name=request.unit_name,
            facilitator=request.facilitator,
            venue=request.venue,
            created_by=current_user["username"],
            department=request.department
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

class CameraRequest(BaseModel):

    camera_id: str
    name: str
    camera_type: str
    location: Optional[str] = None
    department: Optional[str] = None
    source: Optional[str] = None


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
# logged-in user to a course/year it can request a timetable for.

@app.get("/me")
def get_me(
    current_user: dict = Depends(require_roles("STUDENT"))
):

    profile = me_service.get_my_student_profile(
        current_user["username"]
    )

    if profile is None:

        raise HTTPException(
            status_code=404,
            detail="No linked student profile found for this account"
        )

    return profile
