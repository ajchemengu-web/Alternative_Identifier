import cv2
import time
import threading

from .camera_source import CameraSource


class CameraWorker:

    def __init__(
        self,
        camera_source: CameraSource,
        frame_callback=None,
        reconnect_delay=3,
        process_every_n_frames=5
    ):
        self.camera_source = camera_source
        self.frame_callback = frame_callback
        self.reconnect_delay = reconnect_delay

        # Process only every Nth frame
        self.process_every_n_frames = process_every_n_frames
        self.frame_count = 0

        self.capture = None
        self.running = False
        self.thread = None

    # ==========================================
    # CONNECT
    # ==========================================

    def connect(self):

        print(
            f"[{self.camera_source.camera_id}] "
            f"Connecting to {self.camera_source.name}..."
        )

        self.capture = cv2.VideoCapture(
            self.camera_source.source
        )

        if not self.capture.isOpened():

            print(
                f"[{self.camera_source.camera_id}] "
                f"Connection failed."
            )

            self.capture.release()
            self.capture = None

            return False

        print(
            f"[{self.camera_source.camera_id}] "
            f"Connected successfully."
        )

        return True

    # ==========================================
    # START
    # ==========================================

    def start(self):

        if not self.camera_source.enabled:

            print(
                f"[{self.camera_source.camera_id}] "
                f"Camera disabled."
            )

            return

        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=self._run,
            daemon=True
        )

        self.thread.start()

    # ==========================================
    # MAIN LOOP
    # ==========================================

    def _run(self):

        while self.running:

            # -------------------------------
            # CONNECT / RECONNECT
            # -------------------------------

            if self.capture is None:

                if not self.connect():

                    time.sleep(
                        self.reconnect_delay
                    )

                    continue

            # -------------------------------
            # READ FRAME
            # -------------------------------

            success, frame = (
                self.capture.read()
            )

            if not success or frame is None:

                print(
                    f"[{self.camera_source.camera_id}] "
                    f"Frame read failed."
                )

                self.capture.release()
                self.capture = None

                time.sleep(
                    self.reconnect_delay
                )

                continue

            # -------------------------------
            # FRAME COUNTER
            # -------------------------------

            self.frame_count += 1

            # -------------------------------
            # FRAME SAMPLING
            # -------------------------------

            if (
                self.frame_count
                % self.process_every_n_frames
                != 0
            ):
                continue

            # -------------------------------
            # SEND FRAME
            # -------------------------------

            if self.frame_callback:

                self.frame_callback(
                    self.camera_source,
                    frame
                )

    # ==========================================
    # STOP
    # ==========================================

    def stop(self):

        self.running = False

        if self.capture is not None:

            self.capture.release()
            self.capture = None

        print(
            f"[{self.camera_source.camera_id}] "
            f"Stopped."
        )