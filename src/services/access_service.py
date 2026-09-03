import time

from src.access_logger import log_access
from src.services.unknown_service import create_unknown_person


# ==========================================
# ACCESS COOLDOWN
# ==========================================

ACCESS_COOLDOWN = 30

last_logged = {}


# ==========================================
# CHECK IF ACCESS SHOULD BE LOGGED
# ==========================================

def should_log(identifier):

    current_time = time.time()

    if identifier not in last_logged:

        last_logged[identifier] = current_time

        return True


    time_difference = (
        current_time -
        last_logged[identifier]
    )


    if time_difference >= ACCESS_COOLDOWN:

        last_logged[identifier] = current_time

        return True


    return False


# ==========================================
# PROCESS ACCESS DECISION
# ==========================================

def process_access(recognition_result, image=None):

    status = recognition_result.get("status")


    # ======================================
    # VERIFIED STUDENT
    # ======================================

    if status == "STUDENT":

        student_id = recognition_result["student_id"]

        score = recognition_result.get(
            "recognition_score"
        )


        if should_log(student_id):

            log_access(
                person_type="STUDENT",
                person_identifier=student_id,
                entrance="Nyayo Main Gate",
                recognition_score=score,
                decision="VERIFIED"
            )


        return {

            "access_status": "GRANTED",

            "person_type": "STUDENT",

            "message": "Verified student access granted",

            "person": {
                "full_name": recognition_result[
                    "full_name"
                ],

                "admission_number": recognition_result[
                    "admission_number"
                ],

                "hostel": recognition_result[
                    "hostel"
                ],

                "room": recognition_result[
                    "room"
                ]
            },

            "recognition_score": score
        }


    # ======================================
    # ADMITTED GUEST
    # ======================================

    elif status == "ADMITTED_GUEST":

        guest_id = recognition_result["guest_id"]

        score = recognition_result.get(
            "recognition_score"
        )


        if should_log(guest_id):

            log_access(
                person_type="GUEST",
                person_identifier=guest_id,
                entrance="Nyayo Main Gate",
                recognition_score=score,
                decision="AG_VALID"
            )


        return {

            "access_status": "GRANTED",

            "person_type": "ADMITTED_GUEST",

            "message": "Admitted guest access granted",

            "guest_id": guest_id,

            "expires_at": recognition_result[
                "expires_at"
            ],

            "recognition_score": score
        }


    # ======================================
    # UNKNOWN PERSON
    # ======================================

    elif status == "UNKNOWN":

        if image is None:

            return {

                "access_status": "REVIEW_REQUIRED",

                "person_type": "UNKNOWN",

                "message": (
                    "Unknown person detected, "
                    "but no image was provided."
                )
            }


        try:

            unknown_record = create_unknown_person(
                image
            )

            return {

                "access_status": "REVIEW_REQUIRED",

                "person_type": "UNKNOWN",

                "message": (
                    "Unknown person captured. "
                    "Security review required."
                ),

                "unknown_id": unknown_record[
                    "unknown_id"
                ],

                "status": unknown_record[
                    "status"
                ]
            }

        except Exception as error:

            print(
                f"Unknown person capture failed: {error}"
            )

            return {

                "access_status": "REVIEW_REQUIRED",

                "person_type": "UNKNOWN",

                "message": (
                    "Unknown person detected. "
                    "Security review required."
                ),

                "unknown_id": "UNKNOWN"
            }


    # ======================================
    # NO FACE
    # ======================================

    elif status == "NO_FACE":

        return {

            "access_status": "NO_ACTION",

            "person_type": None,

            "message": "No face detected"
        }


    # ======================================
    # FALLBACK
    # ======================================

    return {

        "access_status": "ERROR",

        "message": "Unknown recognition result"
    }