try:
    from src.access_logger import log_access
except ImportError:
    from access_logger import log_access

import time
import cv2
import numpy as np
import sqlite3
import os
from datetime import datetime
from insightface.app import FaceAnalysis

ACCESS_COOLDOWN = 30
last_logged = {}

def should_log(identifier):

    current_time = time.time()

    if identifier not in last_logged:

        last_logged[identifier] = current_time

        return True


    time_difference = (

        current_time -

        last_logged[identifier]

    )


    if time_difference >= ACCESS_COOLDOWN:

        last_logged[identifier] = current_time

        return True


    return False
# ==========================================
# CONFIGURATION
# ==========================================

DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)

STUDENT_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "embeddings"
)

GUEST_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "guests",
    "embeddings"
)

MATCH_THRESHOLD = 0.50

# ==========================================
# ACCESS LOG COOLDOWN
# ==========================================

# ==========================================
# LOAD STUDENTS
# ==========================================

def load_students():

    students = []

    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            student_id,
            full_name,
            admission_number,
            hostel,
            room,
            embedding_file
        FROM students
    """)

    rows = cursor.fetchall()

    connection.close()


    for row in rows:

        (
            student_id,
            full_name,
            admission_number,
            hostel,
            room,
            embedding_file
        ) = row


        embedding_path = os.path.join(
            STUDENT_EMBEDDINGS_FOLDER,
            embedding_file
        )


        if os.path.exists(embedding_path):

            embedding = np.load(embedding_path)

            embedding = (
                embedding /
                np.linalg.norm(embedding)
            )

            students.append({

                "student_id": student_id,

                "full_name": full_name,

                "admission_number": admission_number,

                "hostel": hostel,

                "room": room,

                "embedding": embedding

            })


    return students


# ==========================================
# LOAD ADMITTED GUESTS
# ==========================================

def load_admitted_guests():

    guests = []

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            guest_id,
            embedding_file,
            expires_at
        FROM guests
        WHERE status = ?
    """, ("AG",))


    rows = cursor.fetchall()

    connection.close()


    now = datetime.now()


    for row in rows:

        guest_id, embedding_file, expires_at = row


        # ----------------------------------
        # CHECK EXPIRATION
        # ----------------------------------

        try:

            expiry_time = datetime.fromisoformat(
                expires_at
            )

        except:

            continue


        # Guest has expired
        if now >= expiry_time:

            expire_guest(guest_id)

            continue


        # ----------------------------------
        # LOAD FACE EMBEDDING
        # ----------------------------------

        embedding_path = os.path.join(
            GUEST_EMBEDDINGS_FOLDER,
            embedding_file
        )


        if os.path.exists(embedding_path):

            embedding = np.load(
                embedding_path
            )

            embedding = (
                embedding /
                np.linalg.norm(embedding)
            )


            guests.append({

                "guest_id": guest_id,

                "expires_at": expiry_time,

                "embedding": embedding

            })


    return guests


# ==========================================
# EXPIRE GUEST
# ==========================================

def expire_guest(guest_id):

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    cursor = connection.cursor()


    cursor.execute("""
        UPDATE guests
        SET status = ?
        WHERE guest_id = ?
    """, (
        "EXPIRED",
        guest_id
    ))


    connection.commit()

    connection.close()


# ==========================================
# FIND BEST MATCH
# ==========================================

def find_best_match(
    face_embedding,
    identities
):

    best_match = None

    best_similarity = -1


    for identity in identities:

        similarity = np.dot(

            face_embedding,

            identity["embedding"]

        )


        if similarity > best_similarity:

            best_similarity = similarity

            best_match = identity


    return best_match, best_similarity


# ==========================================
# LOAD DATABASE IDENTITIES
# ==========================================

print("\nLoading Smart Hostel identities...")

students = load_students()

guests = load_admitted_guests()


print(
    f"Students loaded: {len(students)}"
)

print(
    f"Active guests loaded: {len(guests)}"
)


# ==========================================
# LOAD AI MODEL
# ==========================================

print("\nLoading AI model...")

app = FaceAnalysis(

    name="buffalo_s",

    providers=["CPUExecutionProvider"]

)


app.prepare(

    ctx_id=0,

    det_size=(640, 640)

)


print("AI model ready!")


# ==========================================
# OPEN CAMERA
# ==========================================

camera = cv2.VideoCapture(0)


if not camera.isOpened():

    print("Could not open webcam.")

    exit()


print("\n" + "=" * 55)

print("SMART HOSTEL ACCESS SYSTEM STARTED")

print("=" * 55)

print("\nQ → Quit\n")


# ==========================================
# MAIN CAMERA LOOP
# ==========================================

while True:

    success, frame = camera.read()


    if not success:

        print(
            "Could not read camera frame."
        )

        break


    faces = app.get(frame)


    # ======================================
    # PROCESS EVERY FACE
    # ======================================

    for face in faces:


        bbox = face.bbox.astype(int)

        x1, y1, x2, y2 = bbox


        # ----------------------------------
        # NORMALIZE FACE EMBEDDING
        # ----------------------------------

        embedding = face.embedding

        embedding = (

            embedding /

            np.linalg.norm(embedding)

        )


        # ==================================
        # STEP 1: CHECK STUDENTS
        # ==================================

        student_match, student_score = (

            find_best_match(

                embedding,

                students

            )

        )


                # ==================================
        # VERIFIED STUDENT
        # ==================================

        if (
            student_match is not None
            and
            student_score >= MATCH_THRESHOLD
        ):

            # ==================================
            # LOG STUDENT ACCESS
            # ==================================

            identifier = student_match["student_id"]

            if should_log(identifier):

                log_access(
                    person_type="STUDENT",
                    person_identifier=identifier,
                    entrance="Nyayo Main Gate",
                    recognition_score=float(student_score),
                    decision="VERIFIED"
                )


            # ==================================
            # DISPLAY STUDENT
            # ==================================

            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                3
            )

            cv2.putText(
                frame,
                "VERIFIED STUDENT",
                (x1, y1 - 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                student_match["full_name"],
                (x1, y1 - 65),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"ADM: {student_match['admission_number']}",
                (x1, y1 - 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"{student_match['hostel']} | Room {student_match['room']}",
                (x1, y1 - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )


        # ==================================
        # NOT A STUDENT → CHECK GUESTS
        # ==================================

        else:

            guest_match, guest_score = find_best_match(
                embedding,
                guests
            )


            # ==================================
            # VALID ADMITTED GUEST
            # ==================================

            if (
                guest_match is not None
                and
                guest_score >= MATCH_THRESHOLD
            ):

                # ==================================
                # LOG GUEST ACCESS
                # ==================================

                identifier = guest_match["guest_id"]

                if should_log(identifier):

                    log_access(
                        person_type="GUEST",
                        person_identifier=identifier,
                        entrance="Nyayo Main Gate",
                        recognition_score=float(guest_score),
                        decision="AG_VALID"
                    )


                # ==================================
                # DISPLAY GUEST
                # ==================================

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 255),
                    3
                )

                cv2.putText(
                    frame,
                    "AG - ADMITTED GUEST",
                    (x1, y1 - 65),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2
                )

                cv2.putText(
                    frame,
                    guest_match["guest_id"],
                    (x1, y1 - 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2
                )

                expiry_text = (
                    guest_match["expires_at"]
                    .strftime("%Y-%m-%d %H:%M")
                )

                cv2.putText(
                    frame,
                    f"Valid until: {expiry_text}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 255),
                    2
                )


            # ==================================
            # UNKNOWN PERSON
            # ==================================

            else:

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 0, 255),
                    3
                )

                cv2.putText(
                    frame,
                    "UNKNOWN PERSON",
                    (x1, y1 - 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )


            # ==================================
            # STEP 2: CHECK ADMITTED GUESTS
            # ==================================

            guest_match, guest_score = (

                find_best_match(

                    embedding,

                    guests

                )

            )


            # ==================================
            # VALID ADMITTED GUEST
            # ==================================

            if (

                guest_match is not None

                and

                guest_score >= MATCH_THRESHOLD

            ):


                cv2.rectangle(

                    frame,

                    (x1, y1),

                    (x2, y2),

                    (0, 255, 255),

                    3

                )


                cv2.putText(

                    frame,

                    "AG - ADMITTED GUEST",

                    (x1, y1 - 65),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.7,

                    (0, 255, 255),

                    2

                )


                cv2.putText(

                    frame,

                    guest_match["guest_id"],

                    (x1, y1 - 35),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.55,

                    (0, 255, 255),

                    2

                )


                expiry_text = (

                    guest_match["expires_at"]

                    .strftime("%Y-%m-%d %H:%M")

                )


                cv2.putText(

                    frame,

                    f"Valid until: {expiry_text}",

                    (x1, y1 - 10),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.5,

                    (0, 255, 255),

                    2

                )


            # ==================================
            # UNKNOWN PERSON
            # ==================================

            else:


                cv2.rectangle(

                    frame,

                    (x1, y1),

                    (x2, y2),

                    (0, 0, 255),

                    3

                )


                cv2.putText(

                    frame,

                    "UNKNOWN PERSON",

                    (x1, y1 - 15),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.7,

                    (0, 0, 255),

                    2

                )


    # ======================================
    # SYSTEM HEADER
    # ======================================

    cv2.putText(

        frame,

        "SMART HOSTEL ACCESS SYSTEM",

        (20, 35),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.7,

        (255, 255, 255),

        2

    )


    cv2.putText(

        frame,

        f"Students: {len(students)} | Active Guests: {len(guests)}",

        (20, 65),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.55,

        (255, 255, 255),

        2

    )


    # ======================================
    # SHOW CAMERA
    # ======================================

    cv2.imshow(

        "Smart Hostel Security",

        frame

    )


    key = cv2.waitKey(1) & 0xFF


    if key == ord("q"):

        break


# ==========================================
# CLEANUP
# ==========================================

camera.release()

cv2.destroyAllWindows()