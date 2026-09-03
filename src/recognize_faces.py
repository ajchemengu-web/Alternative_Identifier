import cv2
import numpy as np
import os
import json
from insightface.app import FaceAnalysis


# =====================================
# LOAD ENROLLED STUDENTS
# =====================================

EMBEDDINGS_FOLDER = "data/embeddings"

known_students = {}

print("\nLoading enrolled students...")

for filename in os.listdir(EMBEDDINGS_FOLDER):

    if filename.endswith(".npy"):

        student_file = filename.replace(".npy", "")

        embedding_path = os.path.join(
            EMBEDDINGS_FOLDER,
            filename
        )

        metadata_path = os.path.join(
            EMBEDDINGS_FOLDER,
            f"{student_file}.json"
        )

        # Load embedding
        embedding = np.load(embedding_path)

        # Load metadata
        if os.path.exists(metadata_path):

            with open(metadata_path, "r") as file:
                metadata = json.load(file)

            known_students[student_file] = {
                "embedding": embedding,
                "student_id": metadata["student_id"],
                "name": metadata["name"]
            }

            print(
                f"Loaded: {metadata['name']}"
            )


if not known_students:

    print("No enrolled students found.")
    print("Please run enroll_student.py first.")
    exit()


print(
    f"\nTotal enrolled students: {len(known_students)}"
)


# =====================================
# LOAD AI MODEL
# =====================================

print("\nLoading AI face recognition model...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

print("Model loaded successfully!")


# =====================================
# RECOGNITION SETTINGS
# =====================================

# Starting threshold — we will calibrate this later
MATCH_THRESHOLD = 0.50


# =====================================
# OPEN CAMERA
# =====================================

camera = cv2.VideoCapture(2)

if not camera.isOpened():

    print("Could not open webcam.")
    exit()


print("\n" + "=" * 45)
print("REAL-TIME FACE RECOGNITION STARTED")
print("=" * 45)

print("Press Q to quit.\n")


# =====================================
# RECOGNITION LOOP
# =====================================

while True:

    success, frame = camera.read()

    if not success:

        print("Could not read camera frame.")
        break


    # Detect and analyze faces
    faces = app.get(frame)


    # Process every detected face
    for face in faces:

        # Get bounding box
        bbox = face.bbox.astype(int)

        x1, y1, x2, y2 = bbox


        # Get and normalize embedding
        embedding = face.embedding

        embedding = embedding / np.linalg.norm(embedding)


        # -----------------------------
        # FIND BEST MATCH
        # -----------------------------

        best_match = None
        best_similarity = -1


        for student_key, student in known_students.items():

            known_embedding = student["embedding"]

            similarity = np.dot(
                embedding,
                known_embedding
            )


            if similarity > best_similarity:

                best_similarity = similarity

                best_match = student


        # -----------------------------
        # DECIDE IDENTITY
        # -----------------------------

        if best_similarity >= MATCH_THRESHOLD:

            label = (
                f"{best_match['name']} | "
                f"{best_similarity:.2f}"
            )

            status = "MATCHED"

        else:

            label = (
                f"UNKNOWN | "
                f"{best_similarity:.2f}"
            )

            status = "UNKNOWN"


        # -----------------------------
        # DRAW RESULTS
        # -----------------------------

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        cv2.putText(
            frame,
            label,
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )


    # Display number of faces
    cv2.putText(
        frame,
        f"Faces: {len(faces)}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )


    # Show frame
    cv2.imshow(
        "SmartAttend AI - Real-Time Recognition",
        frame
    )


    # Quit
    if cv2.waitKey(1) & 0xFF == ord("q"):

        break


# =====================================
# CLEAN UP
# =====================================

camera.release()
cv2.destroyAllWindows()