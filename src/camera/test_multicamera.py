import time

from src.camera.camera_source import CameraSource
from src.camera.camera_manager import CameraManager

print("TEST MULTI-CAMERA SCRIPT STARTED")

def frame_received(camera, frame):

    print(
        f"[FRAME] "
        f"{camera.camera_id} "
        f"{camera.name} "
        f"{frame.shape}"
    )


manager = CameraManager()


# ==========================================
# LOCAL USB CAMERA
# ==========================================

camera_1 = CameraSource(
    camera_id="CAM-001",
    name="USB Webcam",
    source=1,
    location="Development Machine"
)


manager.add_camera(
    camera_1,
    frame_callback=frame_received
)


# ==========================================
# FUTURE IP CAMERA
# ==========================================

# camera_2 = CameraSource(
#     camera_id="CAM-002",
#     name="Hostel Gate",
#     source="rtsp://username:password@192.168.1.100:554/stream",
#     location="Nyayo Hostel Gate"
# )

# manager.add_camera(
#     camera_2,
#     frame_callback=frame_received
# )


# ==========================================
# START
# ==========================================

manager.start_all()


print("Multi-camera system running.")

try:

    while True:

        time.sleep(1)

except KeyboardInterrupt:

    print("Stopping...")

    manager.stop_all()