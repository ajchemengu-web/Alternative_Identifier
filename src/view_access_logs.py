import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


def get_access_logs():

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            log_id,
            person_type,
            person_identifier,
            entrance,
            recognition_score,
            decision,
            guard_id,
            created_at
        FROM access_logs
        ORDER BY created_at DESC
        LIMIT 50
    """)

    logs = cursor.fetchall()

    connection.close()

    return logs


def get_student(identifier):

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            full_name,
            admission_number,
            hostel,
            room
        FROM students
        WHERE student_id = ?
    """, (identifier,))

    student = cursor.fetchone()

    connection.close()

    return student


def display_logs():

    logs = get_access_logs()

    print("\n" + "=" * 60)
    print("SMART HOSTEL — ACCESS HISTORY")
    print("=" * 60)

    if not logs:

        print("\nNo access records found.")

        return


    for log in logs:

        (
            log_id,
            person_type,
            person_identifier,
            entrance,
            recognition_score,
            decision,
            guard_id,
            created_at
        ) = log


        print("\n" + "-" * 60)

        print(f"TIME: {created_at}")
        print(f"ENTRANCE: {entrance}")


        # ==========================================
        # STUDENT
        # ==========================================

        if person_type == "STUDENT":

            student = get_student(
                person_identifier
            )


            print("\n🎓 VERIFIED STUDENT")


            if student:

                (
                    full_name,
                    admission_number,
                    hostel,
                    room
                ) = student


                print(f"Name: {full_name}")
                print(f"Admission: {admission_number}")
                print(f"Hostel: {hostel}")
                print(f"Room: {room}")

            else:

                print(
                    f"Student ID: {person_identifier}"
                )


        # ==========================================
        # GUEST
        # ==========================================

        elif person_type == "GUEST":

            print("\n🟡 ADMITTED GUEST")

            print(
                f"Guest ID: {person_identifier}"
            )


        # ==========================================
        # OTHER
        # ==========================================

        else:

            print(
                f"\nPerson Type: {person_type}"
            )

            print(
                f"Identifier: {person_identifier}"
            )


        # ==========================================
        # ACCESS DETAILS
        # ==========================================

        print(f"\nDecision: {decision}")

        if recognition_score is not None:

            print(
                f"Recognition Score: "
                f"{recognition_score:.3f}"
            )


        if guard_id:

            print(
                f"Guard: {guard_id}"
            )


    print("\n" + "=" * 60)
    print(f"TOTAL RECORDS DISPLAYED: {len(logs)}")
    print("=" * 60)


if __name__ == "__main__":

    display_logs()