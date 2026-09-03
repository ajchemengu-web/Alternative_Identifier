import cv2
import numpy as np
from insightface.app import FaceAnalysis

print("Loading AI model...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("Could not open webcam.")
    exit()

embedding_1 = None
embedding_2 = None

print("\nINSTRUCTIONS")
print("Press 1 → Capture first face")
print("Change your position slightly")
print("Press 2 → Capture second face")
print("Press C → Compare")
print("Press Q → Quit")

while True:

    success, frame = camera.read()

    if not success:
        break

    cv2.putText(
        frame,
        "1 = Face A | 2 = Face B | C = Compare | Q = Quit",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2
    )

    cv2.imshow("SmartAttend AI - Face Comparison", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break

    # Capture Face A
    elif key == ord("1"):

        faces = app.get(frame)

        if len(faces) == 1:
            embedding_1 = faces[0].embedding
            print("\nFace A captured successfully!")
        else:
            print("Please ensure exactly one face is visible.")

    # Capture Face B
    elif key == ord("2"):

        faces = app.get(frame)

        if len(faces) == 1:
            embedding_2 = faces[0].embedding
            print("\nFace B captured successfully!")
        else:
            print("Please ensure exactly one face is visible.")

    # Compare embeddings
    elif key == ord("c"):

        if embedding_1 is None or embedding_2 is None:
            print("Capture both faces first!")

        else:

            # Normalize embeddings
            emb1 = embedding_1 / np.linalg.norm(embedding_1)
            emb2 = embedding_2 / np.linalg.norm(embedding_2)

            # Cosine similarity
            similarity = np.dot(emb1, emb2)

            print("\n==============================")
            print("FACE COMPARISON RESULT")
            print("==============================")
            print(f"Cosine Similarity: {similarity:.4f}")

            if similarity > 0.5:
                print("RESULT: Likely SAME PERSON ")
            else:
                print("RESULT: Likely DIFFERENT PEOPLE ")

camera.release()
cv2.destroyAllWindows()