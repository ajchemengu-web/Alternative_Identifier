import cv2
import numpy as np
from insightface.app import FaceAnalysis

print("Loading AI model...")

# Initialize InsightFace
app = FaceAnalysis(
    name="buffalo_s",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

# Open webcam
camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("Could not open webcam.")
    exit()

print("Camera started.")
print("Press SPACE to analyze your face.")
print("Press Q to quit.")

while True:

    success, frame = camera.read()

    if not success:
        print("Could not read camera frame.")
        break

    cv2.putText(
        frame,
        "SPACE = Analyze Face | Q = Quit",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    cv2.imshow("SmartAttend AI - Embedding Test", frame)

    key = cv2.waitKey(1) & 0xFF

    # Quit
    if key == ord("q"):
        break

    # Analyze face
    if key == ord(" "):

        print("\nAnalyzing frame...")

        faces = app.get(frame)

        print(f"Faces detected: {len(faces)}")

        if len(faces) == 1:

            face = faces[0]

            embedding = face.embedding

            print("\nFACE EMBEDDING CREATED")
            print(f"Embedding shape: {embedding.shape}")

            print("\nFirst 10 values:")
            print(embedding[:10])

        elif len(faces) == 0:

            print("No face detected. Try again.")

        else:

            print("Multiple faces detected. Please ensure only one person is visible.")

camera.release()
cv2.destroyAllWindows()