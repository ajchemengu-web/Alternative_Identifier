import cv2
import os

# Ask for student's name
student_name = input("Enter student name: ").strip()

if not student_name:
    print("Student name cannot be empty.")
    exit()

# Create a safe folder name
student_folder = student_name.replace(" ", "_")

# Create the path where face images will be saved
save_path = os.path.join("data", "faces", student_folder)

# Create the folder if it doesn't exist
os.makedirs(save_path, exist_ok=True)

# Load OpenCV face detector
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# Open webcam
camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("Error: Could not open webcam")
    exit()

count = 0
max_samples = 20

print("\nEnrollment started!")
print("Look at the camera and slowly move your head.")
print("Press Q to quit.\n")

while True:
    success, frame = camera.read()

    if not success:
        print("Could not read camera frame.")
        break

    # Convert frame to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Detect faces
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(100, 100)
    )

    # Only capture when exactly one face is visible
    if len(faces) == 1 and count < max_samples:

        x, y, w, h = faces[0]

        # Draw rectangle around face
        cv2.rectangle(
            frame,
            (x, y),
            (x + w, y + h),
            (0, 255, 0),
            2
        )

        # Extract the face
        face = frame[y:y+h, x:x+w]

        # Resize for consistent image size
        face = cv2.resize(face, (200, 200))

        # Save image
        image_path = os.path.join(
            save_path,
            f"{student_folder}_{count}.jpg"
        )

        cv2.imwrite(image_path, face)

        count += 1

        # Small delay so we don't capture identical frames
        cv2.waitKey(150)

    # Display progress
    cv2.putText(
        frame,
        f"Samples: {count}/{max_samples}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.imshow("SmartAttend AI - Face Enrollment", frame)

    # Stop when enough samples are captured
    if count >= max_samples:
        print("\nEnrollment complete!")
        break

    # Press Q to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        print("\nEnrollment cancelled.")
        break


camera.release()
cv2.destroyAllWindows()