import cv2
import numpy as np


# ============================================================
# WHAT THIS IS (AND ISN'T)
# ============================================================
#
# This is a passive, single-frame liveness heuristic: it looks for
# signals that a live face in front of a camera tends to have, and
# that a re-captured photo, printout, or phone/tablet screen tends
# to lack or overdo. It runs on one RGB frame with no special
# hardware (no depth sensor, no IR, no challenge/response).
#
# It is NOT a trained anti-spoof classifier. It will not catch a
# high-quality print or replay attack reliably. It exists to close
# the obvious gap opened by auto-admitting verified faces with no
# guard in the loop (see docs/PRD.md §6.1, §13): cheap spoofs get
# caught, and every match still carries a liveness_score for later
# tuning or replacement by a trained model (e.g. a MiniFASNet-style
# classifier) once labeled live/spoof data exists.


# ============================================================
# CONFIGURATION
# ============================================================

LIVENESS_THRESHOLD = 0.55

FACE_CROP_MARGIN_RATIO = 0.25
FACE_ANALYSIS_SIZE = 256

FREQUENCY_WEIGHT = 0.4
TEXTURE_WEIGHT = 0.35
REFLECTION_WEIGHT = 0.25


# ============================================================
# CROP THE FACE OUT OF THE FULL FRAME
# ============================================================

def _crop_face(image, bbox):

    height, width = image.shape[:2]

    x1, y1, x2, y2 = bbox

    box_w = x2 - x1
    box_h = y2 - y1

    margin_x = int(box_w * FACE_CROP_MARGIN_RATIO)
    margin_y = int(box_h * FACE_CROP_MARGIN_RATIO)

    x1 = max(0, x1 - margin_x)
    y1 = max(0, y1 - margin_y)
    x2 = min(width, x2 + margin_x)
    y2 = min(height, y2 + margin_y)

    if x2 <= x1 or y2 <= y1:
        return None

    crop = image[y1:y2, x1:x2]

    return cv2.resize(
        crop,
        (FACE_ANALYSIS_SIZE, FACE_ANALYSIS_SIZE)
    )


# ============================================================
# SIGNAL 1 — FREQUENCY-SPECTRUM PEAKINESS
# ============================================================
#
# A live face photographed directly has a smooth, broad spread of
# spatial frequencies. A face re-captured off a screen shows sharp
# periodic spikes in the mid-to-high frequency band (the pixel/
# moire grid); a face re-captured off a print often collapses that
# same band instead (print blur flattens it out). Both extremes are
# penalized — we want a face that looks like it was photographed
# once, not twice.

def _frequency_score(face_gray):

    spectrum = np.fft.fftshift(
        np.fft.fft2(face_gray.astype(np.float32))
    )

    magnitude = np.log1p(np.abs(spectrum))

    h, w = magnitude.shape
    cy, cx = h / 2, w / 2

    y_idx, x_idx = np.ogrid[:h, :w]

    distance = np.sqrt(
        (x_idx - cx) ** 2 + (y_idx - cy) ** 2
    )

    band = magnitude[
        (distance > 0.12 * min(h, w))
        & (distance < 0.45 * min(h, w))
    ]

    if band.size == 0 or band.mean() <= 1e-6:
        return 0.5

    peakiness = band.max() / band.mean()

    # Empirically, live-camera faces land well under ~6; screen/print
    # recaptures tend to push this higher or collapse it near 1.
    score = 1.0 - abs(peakiness - 3.5) / 6.0

    return float(np.clip(score, 0.0, 1.0))


# ============================================================
# SIGNAL 2 — MICRO-TEXTURE SHARPNESS
# ============================================================
#
# Real skin under a camera has a moderate amount of fine texture
# (pores, stubble, small blemishes). A printed photo tends to be too
# smooth (low variance); a screen recapture tends to show pixel-grid
# aliasing (unnaturally high variance). We reward a middle range
# instead of "sharper is always better".

def _texture_score(face_gray):

    laplacian_variance = cv2.Laplacian(
        face_gray,
        cv2.CV_64F
    ).var()

    # Sweet spot tuned around what a webcam/CCTV lens produces on a
    # face at typical checkpoint distance.
    expected_center = 180.0
    expected_spread = 220.0

    score = 1.0 - abs(
        laplacian_variance - expected_center
    ) / expected_spread

    return float(np.clip(score, 0.0, 1.0))


# ============================================================
# SIGNAL 3 — SPECULAR REFLECTION / GLARE
# ============================================================
#
# Glossy printouts and phone/tablet screens held up to a camera tend
# to throw back a disproportionate amount of near-saturated glare
# compared to skin under ordinary ambient light.

def _reflection_score(face_bgr):

    hsv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2HSV)

    value_channel = hsv[:, :, 2]

    highlight_ratio = float(
        np.mean(value_channel > 245)
    )

    score = 1.0 - np.clip(highlight_ratio / 0.08, 0.0, 1.0)

    return float(score)


# ============================================================
# CHECK LIVENESS FOR ONE DETECTED FACE
# ============================================================

def check_liveness(image, face):

    bbox = face.bbox.astype(int)

    face_crop = _crop_face(image, bbox)

    if face_crop is None:

        return {
            "is_live": False,
            "liveness_score": 0.0,
            "reasons": ["face_crop_failed"]
        }

    face_gray = cv2.cvtColor(
        face_crop,
        cv2.COLOR_BGR2GRAY
    )

    frequency_score = _frequency_score(face_gray)
    texture_score = _texture_score(face_gray)
    reflection_score = _reflection_score(face_crop)

    liveness_score = (
        FREQUENCY_WEIGHT * frequency_score
        + TEXTURE_WEIGHT * texture_score
        + REFLECTION_WEIGHT * reflection_score
    )

    reasons = []

    if frequency_score < 0.4:
        reasons.append("frequency_spectrum_suspicious")

    if texture_score < 0.4:
        reasons.append("texture_out_of_expected_range")

    if reflection_score < 0.4:
        reasons.append("excess_specular_reflection")

    return {
        "is_live": liveness_score >= LIVENESS_THRESHOLD,
        "liveness_score": float(liveness_score),
        "reasons": reasons
    }
