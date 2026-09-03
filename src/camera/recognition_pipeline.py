import cv2

from src.services.recognition_service import app, recognize_embedding
from src.services.access_service import process_access


class RecognitionPipeline:

    def process_frame(self, camera_source, frame):

        camera_id = camera_source.camera_id

        # --------------------------------
        # DISPLAY CAMERA
        # --------------------------------

        display_frame = frame.copy()

        cv2.putText(
            display_frame,
            f"{camera_source.name}",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display_frame,
            f"Location: {camera_source.location}",
            (20, 65),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2
        )

        # --------------------------------
        # FACE DETECTION
        # --------------------------------

        print(f"[{camera_id}] Running face detection...")

        faces = app.get(frame)

        print(f"[{camera_id}] Detected {len(faces)} face(s).")

        # --------------------------------
        # PROCESS FACES
        # --------------------------------

        for face in faces:

            bbox = face.bbox.astype(int)

            x1, y1, x2, y2 = bbox

            # Draw bounding box
            cv2.rectangle(
                display_frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            # Recognition
            recognition_result = recognize_embedding(face.embedding)

            status = recognition_result.get("status", "UNKNOWN")

            print(
                f"[{camera_id}] "
                f"Recognition: {status}"
            )

            # Display recognition result
            cv2.putText(
                display_frame,
                status,
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            # Access processing
            access_result = process_access(
                recognition_result,
                image=frame.copy()
            )

            access_status = access_result.get(
                "access_status",
                "UNKNOWN"
            )

            print(
                f"[{camera_id}] "
                f"ACCESS: {access_status}"
            )

            cv2.putText(
                display_frame,
                f"ACCESS: {access_status}",
                (x1, y2 + 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

        # --------------------------------
        # SHOW CAMERA
        # --------------------------------

        window_name = (
            f"{camera_source.camera_id} - "
            f"{camera_source.name}"
        )

        cv2.imshow(window_name, display_frame)

        # Required for OpenCV window events
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q") or key == 27:

            print("Stopping camera display...")

            cv2.destroyAllWindows()

            return False

        return True