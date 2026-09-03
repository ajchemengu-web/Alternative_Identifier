import time

from src.camera.camera_source import CameraSource
from src.camera.camera_manager import CameraManager
from src.camera.recognition_pipeline import RecognitionPipeline


# ==========================================
# RECOGNITION PIPELINE
# ==========================================

pipeline = RecognitionPipeline()


# ==========================================
# CAMERA MANAGER
# ==========================================

manager = CameraManager()


# ==========================================
# CAMERA 1
# ==========================================

camera_1 = CameraSource(
    camera_id="CAM-001",
    name="Development Webcam",
    source=1,
    location="Development Machine"
)


manager.add_camera(
    camera_1,
    frame_callback=pipeline.process_frame
)


# ==========================================
# START CAMERAS
# ==========================================

manager.start_all()


print(
    "\n"
    "====================================\n"
    " MULTI-CAMERA AI SECURITY RUNNING\n"
    "====================================\n"
)


try:

    while True:

        time.sleep(1)

except KeyboardInterrupt:

    print("\nStopping system...")

    manager.stop_all()