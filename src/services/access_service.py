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
    # WATCHLIST TARGET MATCH (docs/PRD.md §8's
    # SmartAccess "target tracking" —
    # watchlist_service.py)
    # ======================================

    if status == "TARGET_MATCH":

        target_id = recognition_result["target_id"]

        score = recognition_result.get(
            "recognition_score"
        )

        liveness_score = recognition_result.get(
            "liveness_score"
        )


        if not recognition_result.get("is_live", True):

            log_access(
                person_type="TARGET",
                person_identifier=target_id,
                entrance="Nyayo Main Gate",
                recognition_score=score,
                decision="LIVENESS_FAILED",
                liveness_score=liveness_score
            )

            return {

                "access_status": "REVIEW_REQUIRED",

                "person_type": "SUSPECTED_SPOOF",

                "message": (
                    "Face matched an active watchlist target, but "
                    "failed the liveness check. Logged for review."
                ),

                "target_id": target_id,

                "recognition_score": score,

                "liveness_score": liveness_score,

                "liveness_reasons": recognition_result.get(
                    "liveness_reasons",
                    []
                )
            }


        # No should_log() cooldown here, unlike STUDENT/GUEST below —
        # every live sighting of an active target is logged, since
        # that per-entrance, per-timestamp history is what "tracking"
        # a target means (watchlist_service.get_sightings()).

        log_access(
            person_type="TARGET",
            person_identifier=target_id,
            entrance="Nyayo Main Gate",
            recognition_score=score,
            decision="TARGET_ALERT",
            liveness_score=liveness_score
        )

        return {

            "access_status": "DENIED",

            "person_type": "TARGET_ALERT",

            "message": (
                "Face matched an active watchlist target. Access "
                "denied; logged for immediate security review."
            ),

            "target_id": target_id,

            "full_name": recognition_result.get("full_name"),

            "reason": recognition_result.get("reason"),

            "recognition_score": score,

            "liveness_score": liveness_score
        }


    # ======================================
    # VERIFIED STUDENT
    # ======================================

    if status == "STUDENT":

        student_id = recognition_result["student_id"]

        score = recognition_result.get(
            "recognition_score"
        )

        liveness_score = recognition_result.get(
            "liveness_score"
        )


        # Auto-admit only applies to a live face (docs/PRD.md §6.1,
        # §13). A matched identity that fails the liveness check is
        # routed to the guard instead of being auto-admitted.

        if not recognition_result.get("is_live", True):

            if should_log(student_id):

                log_access(
                    person_type="STUDENT",
                    person_identifier=student_id,
                    entrance="Nyayo Main Gate",
                    recognition_score=score,
                    decision="LIVENESS_FAILED",
                    liveness_score=liveness_score
                )

            return {

                "access_status": "REVIEW_REQUIRED",

                "person_type": "SUSPECTED_SPOOF",

                "message": (
                    "Face matched a verified student, but failed "
                    "the liveness check. Routed to guard review "
                    "instead of auto-admit."
                ),

                "claimed_identity": {
                    "full_name": recognition_result[
                        "full_name"
                    ],

                    "admission_number": recognition_result[
                        "admission_number"
                    ]
                },

                "recognition_score": score,

                "liveness_score": liveness_score,

                "liveness_reasons": recognition_result.get(
                    "liveness_reasons",
                    []
                )
            }


        if should_log(student_id):

            log_access(
                person_type="STUDENT",
                person_identifier=student_id,
                entrance="Nyayo Main Gate",
                recognition_score=score,
                decision="VERIFIED",
                liveness_score=liveness_score
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

            "recognition_score": score,

            "liveness_score": liveness_score
        }


    # ======================================
    # ADMITTED GUEST
    # ======================================

    elif status == "ADMITTED_GUEST":

        guest_id = recognition_result["guest_id"]

        score = recognition_result.get(
            "recognition_score"
        )

        liveness_score = recognition_result.get(
            "liveness_score"
        )


        if not recognition_result.get("is_live", True):

            if should_log(guest_id):

                log_access(
                    person_type="GUEST",
                    person_identifier=guest_id,
                    entrance="Nyayo Main Gate",
                    recognition_score=score,
                    decision="LIVENESS_FAILED",
                    liveness_score=liveness_score
                )

            return {

                "access_status": "REVIEW_REQUIRED",

                "person_type": "SUSPECTED_SPOOF",

                "message": (
                    "Face matched a previously admitted guest, but "
                    "failed the liveness check. Routed to guard "
                    "review instead of auto-admit."
                ),

                "guest_id": guest_id,

                "recognition_score": score,

                "liveness_score": liveness_score,

                "liveness_reasons": recognition_result.get(
                    "liveness_reasons",
                    []
                )
            }


        if should_log(guest_id):

            log_access(
                person_type="GUEST",
                person_identifier=guest_id,
                entrance="Nyayo Main Gate",
                recognition_score=score,
                decision="AG_VALID",
                liveness_score=liveness_score
            )


        return {

            "access_status": "GRANTED",

            "person_type": "ADMITTED_GUEST",

            "message": "Admitted guest access granted",

            "guest_id": guest_id,

            "expires_at": recognition_result[
                "expires_at"
            ],

            "recognition_score": score,

            "liveness_score": liveness_score
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