import numpy as np

from src.services import liveness_service as ls


class FakeFace:

    def __init__(self, bbox):

        self.bbox = np.array(bbox, dtype=np.float32)


if __name__ == "__main__":

    print("Testing liveness_service...")

    # ------------------------------------------------------------
    # _crop_face
    # ------------------------------------------------------------

    image = np.zeros((480, 640, 3), dtype=np.uint8)

    crop = ls._crop_face(image, (220, 140, 420, 380))
    assert crop is not None
    assert crop.shape == (ls.FACE_ANALYSIS_SIZE, ls.FACE_ANALYSIS_SIZE, 3)
    print(f"Valid bbox crops + resizes to {crop.shape}")

    degenerate_crop = ls._crop_face(image, (300, 200, 300, 200))
    assert degenerate_crop is None
    print("A degenerate (zero-area) bbox returns None, as expected")

    out_of_bounds_crop = ls._crop_face(image, (-9999, -9999, -9998, -9998))
    assert out_of_bounds_crop is None
    print("A fully out-of-frame bbox returns None, as expected")

    # ------------------------------------------------------------
    # _texture_score rewards a *middle* range (real skin texture),
    # penalizing both extremes: a perfectly flat crop (print-like)
    # and a pixel-grid-noisy one (screen-recapture-like) both score
    # low, while a moderately textured crop scores near the top.
    # ------------------------------------------------------------

    rng = np.random.default_rng(seed=42)

    flat_gray = np.full((256, 256), 180, dtype=np.uint8)
    flat_texture_score = ls._texture_score(flat_gray)
    assert flat_texture_score < 0.4
    print(f"Perfectly flat crop scores low on texture: {flat_texture_score:.3f}")

    noisy_gray = rng.integers(0, 255, (256, 256), dtype=np.uint8)
    noisy_texture_score = ls._texture_score(noisy_gray)
    assert noisy_texture_score < 0.4
    print(f"Pixel-grid-noisy crop also scores low on texture: {noisy_texture_score:.3f}")

    # A gentle amount of grain around a mid-tone base — the amount
    # of fine detail a real face under a camera actually produces —
    # lands right in the sweet spot both extremes above missed.
    moderate_gray = np.clip(
        150 + rng.normal(0, 3, (256, 256)), 0, 255
    ).astype(np.uint8)
    moderate_texture_score = ls._texture_score(moderate_gray)
    assert moderate_texture_score > flat_texture_score
    assert moderate_texture_score > noisy_texture_score
    print(f"Moderately textured (skin-like) crop scores highest: {moderate_texture_score:.3f}")

    # ------------------------------------------------------------
    # _reflection_score — heavy near-saturated glare scores low;
    # an ordinary mid-tone crop scores at (or near) the maximum
    # ------------------------------------------------------------

    glare_bgr = np.zeros((256, 256, 3), dtype=np.uint8)
    glare_bgr[:] = (250, 250, 250)  # near-white everywhere -> glare
    glare_score = ls._reflection_score(glare_bgr)
    assert glare_score < 0.4
    print(f"Near-white (glare-like) crop scores low on reflection: {glare_score:.3f}")

    normal_bgr = np.zeros((256, 256, 3), dtype=np.uint8)
    normal_bgr[:] = (120, 100, 90)  # ordinary mid-tone skin-ish value
    normal_score = ls._reflection_score(normal_bgr)
    assert normal_score > glare_score
    assert normal_score == 1.0
    print(f"Ordinary mid-tone crop scores at the maximum: {normal_score:.3f}")

    # ------------------------------------------------------------
    # check_liveness — full pipeline: shape/type of the result, and
    # the face-crop-failure short-circuit path
    # ------------------------------------------------------------

    face = FakeFace(bbox=[220, 140, 420, 380])
    frame = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)

    result = ls.check_liveness(frame, face)
    assert isinstance(result["is_live"], bool)
    assert isinstance(result["liveness_score"], float)
    assert 0.0 <= result["liveness_score"] <= 1.0
    assert isinstance(result["reasons"], list)
    print("check_liveness returns a well-shaped result ->", result)

    failing_face = FakeFace(bbox=[-500, -500, -400, -400])
    failed_result = ls.check_liveness(frame, failing_face)
    assert failed_result == {
        "is_live": False,
        "liveness_score": 0.0,
        "reasons": ["face_crop_failed"],
    }
    print("An unusable bbox short-circuits to is_live=False, as expected")

    print("\nliveness_service smoke test passed.")
