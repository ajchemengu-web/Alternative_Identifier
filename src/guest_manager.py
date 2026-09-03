import cv2
import numpy as np
import sqlite3
import os
import uuid
from datetime import datetime
from insightface.app import FaceAnalysis


# ==========================================
# CONFIGURATION
# ==========================================

DATABASE_PATH = os.path.join("data", "smarthostel.db")

GUEST_PHOTOS_FOLDER = os.path.join(
    "data",
    "guests",
    "photos"
)

GUEST_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "guests",
    "embeddings"
)


os.makedirs(
    GUEST_PHOTOS_FOLDER,
    exist_ok=True
)

os.makedirs(
    GUEST_EMBEDDINGS_FOLDER,
    exist_ok=True
)


# ==========================================
# LOAD AI MODEL
# ==========================================

print("Loading AI face recognition model...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

print("AI model ready!")


# ==========================================
# GENERATE GUEST ID
# ==========================================

def generate_guest_id():

    unique_code = uuid.uuid4().hex[:8].upper()

    return f"GUEST-{unique_code}"


# ==========================================
# OPEN CAMERA
# ==========================================

camera = cv2.VideoCapture(0)

if not camera.isOpened():

    print("Could not open webcam.")

    exit()


print("\n" + "=" * 50)
print("SMART HOSTEL - GUEST CAPTURE")
print("=" * 50)

print("\nInstructions:")
print("C → Capture guest")
print("Q → Quit")

print("\nMake sure ONLY ONE face is visible.\n")


# ==========================================
# CAMERA LOOP
# ==========================================

while True:

    success, frame = camera.read()

    if not success:

        print("Could not read camera frame.")

        break


    faces = app.get(frame)


    # --------------------------------------
    # DRAW FACE DETECTION
    # --------------------------------------

    for face in faces:

        bbox = face.bbox.astype(int)

        x1, y1, x2, y2 = bbox

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 255),
            2
        )


    # --------------------------------------
    # DISPLAY INSTRUCTIONS
    # --------------------------------------

    cv2.putText(
        frame,
        "UNKNOWN GUEST CAPTURE",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )

    cv2.putText(
        frame,
        "C = Capture | Q = Quit",
        (20, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2
    )


    cv2.imshow(
        "Smart Hostel - Guest Capture",
        frame
    )


    key = cv2.waitKeyEx(1)


    # =====================================
    # QUIT
    # =====================================

    if key == ord("q"):

        print("\nGuest capture cancelled.")

        break


    # =====================================
    # CAPTURE GUEST
    # =====================================

    elif key in [ord("c"), ord("C")]:

        # No face
        if len(faces) == 0:

            print("No face detected.")

            continue


        # Multiple faces
        if len(faces) > 1:

            print(
                "Multiple faces detected."
            )

            print(
                "Only one guest should be captured."
            )

            continue


        # =================================
        # CREATE GUEST ID
        # =================================

        guest_id = generate_guest_id()


        # =================================
        # GET FACE EMBEDDING
        # =================================

        embedding = faces[0].embedding

        embedding = (
            embedding /
            np.linalg.norm(embedding)
        )


        # =================================
        # SAVE PHOTO
        # =================================

        photo_filename = f"{guest_id}.jpg"

        photo_path = os.path.join(
            GUEST_PHOTOS_FOLDER,
            photo_filename
        )

        cv2.imwrite(
            photo_path,
            frame
        )


        # =================================
        # SAVE EMBEDDING
        # =================================

        embedding_filename = f"{guest_id}.npy"

        embedding_path = os.path.join(
            GUEST_EMBEDDINGS_FOLDER,
            embedding_filename
        )

        np.save(
            embedding_path,
            embedding
        )


        # =================================
        # SAVE TO DATABASE
        # =================================

        try:

            connection = sqlite3.connect(
                DATABASE_PATH
            )

            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO guests (
                    guest_id,
                    photo_path,
                    embedding_file,
                    status
                )
                VALUES (?, ?, ?, ?)
            """, (
                guest_id,
                photo_path,
                embedding_filename,
                "PENDING"
            ))

            connection.commit()

            print("\n" + "=" * 45)
            print("📸 GUEST CAPTURED SUCCESSFULLY")
            print("=" * 45)

            print(f"Guest ID: {guest_id}")
            print("Status: PENDING")

        except Exception as error:

            print("\nDatabase error:")
            print(error)

            # Clean up files if database save fails
            if os.path.exists(photo_path):
                os.remove(photo_path)

            if os.path.exists(embedding_path):
                os.remove(embedding_path)

        finally:

            if 'connection' in locals():
                connection.close()


        # Capture only one guest per run
        break


# ==========================================
# CLEANUP
# ==========================================

camera.release()
cv2.destroyAllWindows()