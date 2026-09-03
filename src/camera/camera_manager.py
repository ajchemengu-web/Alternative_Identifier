from .camera_worker import CameraWorker
from .camera_source import CameraSource


class CameraManager:

    def __init__(self):

        self.workers = {}

    # ==========================================
    # ADD CAMERA
    # ==========================================

    def add_camera(
        self,
        camera_source: CameraSource,
        frame_callback=None
    ):

        if camera_source.camera_id in self.workers:

            raise ValueError(
                f"Camera "
                f"{camera_source.camera_id} "
                f"already exists."
            )

        worker = CameraWorker(
            camera_source=camera_source,
            frame_callback=frame_callback
        )

        self.workers[
            camera_source.camera_id
        ] = worker

        print(
            f"Added camera: "
            f"{camera_source.camera_id}"
        )

    # ==========================================
    # START ONE CAMERA
    # ==========================================

    def start_camera(self, camera_id):

        worker = self.workers.get(
            camera_id
        )

        if worker is None:

            raise ValueError(
                f"Camera {camera_id} not found."
            )

        worker.start()

    # ==========================================
    # START ALL CAMERAS
    # ==========================================

    def start_all(self):

        for worker in self.workers.values():

            worker.start()

    # ==========================================
    # STOP ONE CAMERA
    # ==========================================

    def stop_camera(self, camera_id):

        worker = self.workers.get(
            camera_id
        )

        if worker:

            worker.stop()

    # ==========================================
    # STOP ALL CAMERAS
    # ==========================================

    def stop_all(self):

        for worker in self.workers.values():

            worker.stop()

    # ==========================================
    # LIST CAMERAS
    # ==========================================

    def list_cameras(self):

        return list(
            self.workers.keys()
        )