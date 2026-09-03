import cv2
import numpy as np
import os
import sqlite3
from insightface.app import FaceAnalysis


# =====================================
# CONFIGURATION
# =====================================

DATABASE_PATH = os.path.join("data", "smarthostel.db")
EMBEDDINGS_FOLDER = os.path.join("data", "embeddings")

MAX_SAMPLES = 10

os.makedirs(EMBEDDINGS_FOLDER, exist_ok=True)


# =====================================
# LOAD AI MODEL
# =====================================

print("Loading face recognition model...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

print("Model loaded successfully!\n")


# =====================================
# STUDENT INFORMATION
# =====================================

print("=" * 45)
print("SMART HOSTEL - STUDENT ENROLLMENT")
print("=" * 45)

student_id = input("Student ID: ").strip()
full_name = input("Full Name: ").strip()
admission_number = input("Admission Number: ").strip()
hostel = input("Hostel: ").strip()
room = input("Room Number: ").strip()


if not all([
    student_id,
    full_name,
    admission_number,
    hostel,
    room
]):
    print("\n All fields are required.")
    exit()


# Make ID safe for filenames
safe_student_id = (
    student_id
    .replace("/", "-")
    .replace("\\", "-")
    .replace(" ", "_")
)


# =====================================
# OPEN CAMERA
# =====================================

camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print(" Could not open webcam.")
    exit()


embeddings = []


print("\n" + "=" * 45)
print("FACE ENROLLMENT STARTED")
print("=" * 45)

print("\nSPACE → Capture sample")
print("Q → Cancel")

print(f"\nCapture {MAX_SAMPLES} good samples.")
print("Use slightly different angles.\n")


# =====================================
# ENROLLMENT LOOP
# =====================================

while True:

    success, frame = camera.read()

    if not success:
        print(" Could not read camera frame.")
        break


    faces = app.get(frame)


    # Draw face boxes
    for face in faces:

        bbox = face.bbox.astype(int)

        x1, y1, x2, y2 = bbox

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )


    # Display information
    cv2.putText(
        frame,
        f"{full_name}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Samples: {len(embeddings)}/{MAX_SAMPLES}",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        "SPACE = Capture | Q = Cancel",
        (20, 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2
    )


    cv2.imshow(
        "SmartHostel - Student Enrollment",
        frame
    )


    key = cv2.waitKeyEx(1)


    # Cancel enrollment
    if key == ord("q"):

        print("\nEnrollment cancelled.")

        camera.release()
        cv2.destroyAllWindows()

        exit()


    # Capture sample
    elif key == 32:

        if len(faces) == 0:

            print("❌ No face detected.")

        elif len(faces) > 1:

            print("❌ Multiple faces detected. Only one person allowed.")

        else:

            embedding = faces[0].embedding

            # Normalize
            embedding = embedding / np.linalg.norm(embedding)

            embeddings.append(embedding)

            print(
                f"Sample {len(embeddings)}/{MAX_SAMPLES}"
            )


    # Stop after enough samples
    if len(embeddings) >= MAX_SAMPLES:

        break


# =====================================
# CLEAN UP CAMERA
# =====================================

camera.release()
cv2.destroyAllWindows()


# =====================================
# CREATE BIOMETRIC TEMPLATE
# =====================================

print("\nCreating biometric template...")

embeddings_array = np.array(embeddings)

final_embedding = np.mean(
    embeddings_array,
    axis=0
)

# Normalize final embedding
final_embedding = (
    final_embedding /
    np.linalg.norm(final_embedding)
)


# =====================================
# SAVE EMBEDDING
# =====================================

embedding_filename = f"{safe_student_id}.npy"

embedding_path = os.path.join(
    EMBEDDINGS_FOLDER,
    embedding_filename
)

np.save(
    embedding_path,
    final_embedding
)

print("Face template saved.")


# =====================================
# SAVE STUDENT TO DATABASE
# =====================================

try:

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO students (
            student_id,
            full_name,
            admission_number,
            hostel,
            room,
            embedding_file
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        student_id,
        full_name,
        admission_number,
        hostel,
        room,
        embedding_filename
    ))

    connection.commit()

    print("Student saved to database.")

except sqlite3.IntegrityError as error:

    print("\n STUDENT ALREADY EXISTS")
    print(error)

    # Remove embedding we just created
    if os.path.exists(embedding_path):
        os.remove(embedding_path)

finally:

    if 'connection' in locals():
        connection.close()


# =====================================
# SUCCESS
# =====================================

print("\n" + "=" * 45)
print("STUDENT ENROLLMENT COMPLETE")
print("=" * 45)

print(f"Name: {full_name}")
print(f"Admission Number: {admission_number}")
print(f"Hostel: {hostel}")
print(f"Room: {room}")