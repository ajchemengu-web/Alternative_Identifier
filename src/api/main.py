from fastapi import FastAPI, UploadFile, File, HTTPException
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
def get_students():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            student_id,
            full_name,
            admission_number,
            hostel,
            room
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
def get_guests():

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
def get_access_logs():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            person_type,
            person_identifier,
            entrance,
            recognition_score,
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
async def recognize(file: UploadFile = File(...)):

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

def get_pending_persons():

    pending = get_pending_unknowns()

    return {

        "total_pending": len(pending),

        "unknown_persons": pending

    }

@app.post("/guard/admit/{unknown_id}")

def admit_person(
    unknown_id: str
):

    result = admit_unknown_person(
        unknown_id
    )

    return result

@app.post("/guard/reject/{unknown_id}")

def reject_person(
    unknown_id: str
):

    result = reject_unknown_person(
        unknown_id
    )

    return result


# ==========================================
# ENROLLMENT DASHBOARD (docs/PRD.md §5)
# ==========================================
#
# No session/auth middleware protects these yet — see the note at
# the top of src/services/auth_service.py. In particular, nothing
# stops an unauthenticated caller from hitting /enroll directly;
# that needs to change before this is exposed beyond a trusted admin
# tool, same as the rest of this prototype's open endpoints.

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
def enroll(request: EnrollRequest):

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
def complete_temporary_admin_task(username: str):

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
    files: List[UploadFile] = File(...)
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
            images=images
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    return result
