import cv2
import time
import math

from src.services.recognition_service import (
    app,
    recognize_embedding
)

from src.services.access_service import (
    process_access
)


# ==========================================
# CONFIGURATION
# ==========================================

CAMERA_INDEX = 1

WINDOW_NAME = "SMART HOSTEL - LIVE SECURITY"

TRACK_DISTANCE_THRESHOLD = 120

TRACK_TIMEOUT = 2.0


# ==========================================
# ACTIVE TRACKS
# ==========================================

active_tracks = {}

next_track_id = 1


# ==========================================
# GET CENTER OF BOUNDING BOX
# ==========================================

def get_center(bbox):

    x1, y1, x2, y2 = bbox

    return (

        (x1 + x2) / 2,

        (y1 + y2) / 2

    )


# ==========================================
# CALCULATE DISTANCE
# ==========================================

def calculate_distance(center1, center2):

    return math.sqrt(

        (center1[0] - center2[0]) ** 2 +

        (center1[1] - center2[1]) ** 2

    )


# ==========================================
# REMOVE EXPIRED TRACKS
# ==========================================

def remove_expired_tracks():

    current_time = time.time()

    expired_tracks = []


    for track_id, track in active_tracks.items():

        time_since_seen = (

            current_time -

            track["last_seen"]

        )


        if time_since_seen > TRACK_TIMEOUT:

            expired_tracks.append(track_id)


    for track_id in expired_tracks:

        print(
            f"TRACK-{track_id} left camera view"
        )

        del active_tracks[track_id]


# ==========================================
# FIND EXISTING TRACK
# ==========================================

def find_existing_track(bbox):

    face_center = get_center(bbox)

    best_track_id = None

    best_distance = float("inf")


    for track_id, track in active_tracks.items():

        track_center = get_center(
            track["bbox"]
        )


        distance = calculate_distance(

            face_center,

            track_center

        )


        if distance < best_distance:

            best_distance = distance

            best_track_id = track_id


    if (

        best_track_id is not None

        and

        best_distance < TRACK_DISTANCE_THRESHOLD

    ):

        return best_track_id


    return None


# ==========================================
# OPEN CAMERA
# ==========================================

camera = cv2.VideoCapture(
    CAMERA_INDEX
)


if not camera.isOpened():

    print("Could not open external webcam.")

    exit()


print(" External camera connected!")
print(" Face recognition system ready!")
print(" Smart Hostel live security started!")


# ==========================================
# MAIN CAMERA LOOP
# ==========================================

while True:

    success, frame = camera.read()


    if not success:

        print(" Could not read camera frame.")

        break


    # ======================================
    # DETECT ALL FACES
    # ======================================

    faces = app.get(frame)


    # ======================================
    # PROCESS EACH FACE
    # ======================================

    for face in faces:


        bbox = face.bbox.astype(int)


        # ==================================
        # FIND EXISTING TRACK
        # ==================================

        track_id = find_existing_track(
            bbox
        )


        # ==================================
        # CREATE NEW TRACK
        # ==================================

        if track_id is None:

            track_id = next_track_id

            next_track_id += 1


            active_tracks[track_id] = {

                "bbox": bbox,

                "last_seen": time.time(),

                "processed": False,

                "status": "DETECTED",

                "result": None

            }


            print(
                f" New face → TRACK-{track_id}"
            )


        # ==================================
        # UPDATE TRACK
        # ==================================

        active_tracks[track_id]["bbox"] = bbox

        active_tracks[track_id]["last_seen"] = time.time()


        # ==================================
        # PROCESS ONLY ONCE
        # ==================================

        if not active_tracks[track_id]["processed"]:

            print(
                f" Recognizing TRACK-{track_id}"
            )


            # ------------------------------
            # CROP FACE
            # ------------------------------

            x1, y1, x2, y2 = bbox

            margin = 20


            x1_crop = max(
                0,
                x1 - margin
            )

            y1_crop = max(
                0,
                y1 - margin
            )

            x2_crop = min(
                frame.shape[1],
                x2 + margin
            )

            y2_crop = min(
                frame.shape[0],
                y2 + margin
            )


            face_image = frame[
                y1_crop:y2_crop,
                x1_crop:x2_crop
            ]


            # ------------------------------
            # RECOGNITION
            # ------------------------------

            recognition_result = recognize_embedding(
                face.embedding
            )

            # ------------------------------
            # DEBUGGING OUTPUT
            # ------------------------------

            print(
                f" TRACK-{track_id} | "
                f"Status: {recognition_result.get('status')} | "
                f"Score: {recognition_result.get('recognition_score', 'N/A')}"
            )

            # ------------------------------
            # ACCESS DECISION
            # ------------------------------

            access_result = process_access(
    recognition_result,
    image=frame.copy()
)


            # ------------------------------
            # SAVE RESULT
            # ------------------------------

            active_tracks[track_id][
                "result"
            ] = access_result


            active_tracks[track_id][
                "recognition_result"
            ] = recognition_result


            active_tracks[track_id][
                "processed"
            ] = True


            active_tracks[track_id][
                "status"
            ] = access_result.get(

                "access_status",

                "PROCESSED"

            )


            print(
                f"TRACK-{track_id}: "
                f"{active_tracks[track_id]['status']}"
            )


        # ==================================
        # DRAW RESULTS
        # ==================================

        x1, y1, x2, y2 = bbox

        result = active_tracks[track_id].get(
            "result"
        )


        status = active_tracks[track_id][
            "status"
        ]


        # ----------------------------------
        # CHOOSE DISPLAY COLOR
        # ----------------------------------

        if status == "GRANTED":

            color = (0, 255, 0)

        elif status == "REVIEW_REQUIRED":

            color = (0, 0, 255)

        else:

            color = (0, 255, 255)


        # ----------------------------------
        # FACE BOX
        # ----------------------------------

        cv2.rectangle(

            frame,

            (x1, y1),

            (x2, y2),

            color,

            3

        )


        # ----------------------------------
        # TRACK ID
        # ----------------------------------

        cv2.putText(

            frame,

            f"TRACK-{track_id}",

            (x1, y1 - 75),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            color,

            2

        )


        # ----------------------------------
        # ACCESS STATUS
        # ----------------------------------

        cv2.putText(

            frame,

            status,

            (x1, y1 - 50),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            color,

            2

        )


        # ----------------------------------
        # STUDENT INFORMATION
        # ----------------------------------

        if result:

            if result.get("person_type") == "STUDENT":

                person = result.get(
                    "person",
                    {}
                )


                cv2.putText(

                    frame,

                    person.get(
                        "full_name",
                        "Student"
                    ),

                    (x1, y1 - 25),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.55,

                    color,

                    2

                )


                cv2.putText(

                    frame,

                    person.get(
                        "admission_number",
                        ""
                    ),

                    (x1, y2 + 25),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.5,

                    color,

                    2

                )


            # ------------------------------
            # ADMITTED GUEST
            # ------------------------------

            elif result.get(
                "person_type"
            ) == "ADMITTED_GUEST":

                cv2.putText(

                    frame,

                    "ADMITTED GUEST",

                    (x1, y1 - 25),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.55,

                    color,

                    2

                )


            # ------------------------------
            # UNKNOWN
            # ------------------------------

            elif result.get(
                "person_type"
            ) == "UNKNOWN":

                unknown_id = result.get(

                    "unknown_id",

                    "UNKNOWN"

                )


                cv2.putText(

                    frame,

                    unknown_id,

                    (x1, y1 - 25),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.55,

                    color,

                    2

                )


    # ======================================
    # REMOVE PEOPLE WHO LEFT
    # ======================================

    remove_expired_tracks()


    # ======================================
    # SYSTEM HEADER
    # ======================================

    cv2.putText(

        frame,

        "SMART HOSTEL - LIVE AI SECURITY",

        (20, 35),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.7,

        (255, 255, 255),

        2

    )


    cv2.putText(

        frame,

        f"Active Faces: {len(active_tracks)}",

        (20, 65),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.55,

        (255, 255, 255),

        2

    )


    # ======================================
    # DISPLAY
    # ======================================

    cv2.imshow(

        WINDOW_NAME,

        frame

    )


    # ======================================
    # EXIT
    # ======================================

    key = cv2.waitKey(1) & 0xFF


    if key == ord("q") or key == 27:

        break


# ==========================================
# CLEANUP
# ==========================================

camera.release()

cv2.destroyAllWindows()

print(" Smart Hostel live security stopped.")