import cv2
import numpy as np
import sqlite3
import os
from insightface.app import FaceAnalysis


# =====================================
# CONFIGURATION
# =====================================

DATABASE_PATH = os.path.join("data", "smarthostel.db")
EMBEDDINGS_FOLDER = os.path.join("data", "embeddings")

MATCH_THRESHOLD = 0.50


# =====================================
# LOAD STUDENTS FROM DATABASE
# =====================================

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
            EMBEDDINGS_FOLDER,
            embedding_file
        )


        if os.path.exists(embedding_path):

            embedding = np.load(embedding_path)

            # Safety: normalize embedding
            embedding = embedding / np.linalg.norm(embedding)

            students.append({
                "student_id": student_id,
                "full_name": full_name,
                "admission_number": admission_number,
                "hostel": hostel,
                "room": room,
                "embedding": embedding
            })

            print(f"Loaded: {full_name}")

        else:

            print(
                f" Embedding missing for {full_name}"
            )


    return students


print("\nLoading registered students...")

students = load_students()

if not students:

    print("No students found in database.")
    exit()

print(
    f"\nTotal registered students: {len(students)}"
)


# =====================================
# LOAD AI MODEL
# =====================================

print("\nLoading AI recognition model...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

print("✅ AI model ready!")


# =====================================
# OPEN CAMERA
# =====================================

camera = cv2.VideoCapture(1)

if not camera.isOpened():

    print("Could not open webcam.")
    exit()


print("\n" + "=" * 50)
print("SMART HOSTEL ACCESS SYSTEM STARTED")
print("=" * 50)

print("\nQ → Quit\n")


# =====================================
# MAIN RECOGNITION LOOP
# =====================================

while True:

    success, frame = camera.read()

    if not success:

        print("Could not read camera frame.")
        break


    faces = app.get(frame)


    for face in faces:

        # ---------------------------------
        # FACE LOCATION
        # ---------------------------------

        bbox = face.bbox.astype(int)

        x1, y1, x2, y2 = bbox


        # ---------------------------------
        # NORMALIZE EMBEDDING
        # ---------------------------------

        embedding = face.embedding

        embedding = (
            embedding /
            np.linalg.norm(embedding)
        )


        # ---------------------------------
        # FIND BEST MATCH
        # ---------------------------------

        best_student = None

        best_similarity = -1


        for student in students:

            similarity = np.dot(
                embedding,
                student["embedding"]
            )


            if similarity > best_similarity:

                best_similarity = similarity

                best_student = student


        # ---------------------------------
        # VERIFIED STUDENT
        # ---------------------------------

        if best_similarity >= MATCH_THRESHOLD:

            # Bounding box
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                3
            )


            # Student name
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
                best_student["full_name"],
                (x1, y1 - 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"ADM: {best_student['admission_number']}",
                (x1, y1 - 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"{best_student['hostel']} | Room {best_student['room']}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2
            )


        # ---------------------------------
        # UNKNOWN PERSON
        # ---------------------------------

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


    # =====================================
    # SYSTEM STATUS
    # =====================================

    cv2.putText(
        frame,
        f"Registered Students: {len(students)}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )


    cv2.putText(
        frame,
        "SMART HOSTEL ACCESS SYSTEM",
        (20, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2
    )


    # =====================================
    # DISPLAY
    # =====================================

    cv2.imshow(
        "Smart Hostel Security",
        frame
    )


    # Quit
    if cv2.waitKey(1) & 0xFF == ord("q"):

        break


# =====================================
# CLEANUP
# =====================================

camera.release()
cv2.destroyAllWindows()