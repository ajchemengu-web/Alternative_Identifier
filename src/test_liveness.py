import numpy as np

from src.services.liveness_service import check_liveness


class FakeFace:

    def __init__(self, bbox):

        self.bbox = np.array(bbox, dtype=np.float32)


if __name__ == "__main__":

    print("Testing liveness heuristic on synthetic frames...")

    # A flat, smooth crop (roughly simulates a print/blur recapture)
    smooth_image = np.full(
        (480, 640, 3),
        180,
        dtype=np.uint8
    )

    # A face-sized region of camera-like noise (roughly simulates a
    # real, texture-rich live capture)
    noisy_image = np.random.randint(
        0,
        255,
        (480, 640, 3),
        dtype=np.uint8
    )

    face = FakeFace(bbox=[220, 140, 420, 380])

    smooth_result = check_liveness(smooth_image, face)
    noisy_result = check_liveness(noisy_image, face)

    print(f"Smooth/flat crop  -> {smooth_result}")
    print(f"Noisy/textured crop -> {noisy_result}")

    print("Liveness heuristic ran without errors.")
