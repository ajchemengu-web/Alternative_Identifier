import sqlite3
import os
from datetime import datetime, timedelta


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


# ==========================================
# GET PENDING GUESTS
# ==========================================

def get_pending_guests():

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            guest_id,
            photo_path,
            status,
            created_at
        FROM guests
        WHERE status = ?
        ORDER BY created_at DESC
    """, ("PENDING",))

    guests = cursor.fetchall()

    connection.close()

    return guests


# ==========================================
# ADMIT GUEST
# ==========================================

def admit_guest(guest_id, guard_name):

    admitted_at = datetime.now()

    expires_at = admitted_at + timedelta(hours=24)


    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE guests
        SET
            status = ?,
            admitted_by = ?,
            admitted_at = ?,
            expires_at = ?
        WHERE guest_id = ?
    """, (
        "AG",
        guard_name,
        admitted_at.isoformat(),
        expires_at.isoformat(),
        guest_id
    ))

    connection.commit()

    connection.close()

    return expires_at


# ==========================================
# REJECT GUEST
# ==========================================

def reject_guest(guest_id, guard_name):

    rejected_at = datetime.now()


    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE guests
        SET
            status = ?,
            rejected_by = ?,
            rejected_at = ?
        WHERE guest_id = ?
    """, (
        "REJECTED",
        guard_name,
        rejected_at.isoformat(),
        guest_id
    ))

    connection.commit()

    connection.close()


# ==========================================
# MAIN PROGRAM
# ==========================================

print("\n" + "=" * 50)
print("SMART HOSTEL SECURITY - GUARD DECISION")
print("=" * 50)


guard_name = input("\nGuard name: ").strip()

if not guard_name:

    print("Guard name is required.")
    exit()


guests = get_pending_guests()


if not guests:

    print("\nNo pending guests.")

    exit()


print("\nPENDING GUESTS:\n")


for index, guest in enumerate(guests, start=1):

    guest_id, photo_path, status, created_at = guest

    print(f"{index}. Guest ID: {guest_id}")
    print(f"   Captured: {created_at}")
    print()


# ==========================================
# SELECT GUEST
# ==========================================

try:

    choice = int(
        input("Select guest number: ")
    )

    selected_guest = guests[choice - 1]

except (ValueError, IndexError):

    print("Invalid selection.")

    exit()


guest_id = selected_guest[0]


print("\nSelected Guest:")

print(guest_id)


# ==========================================
# GUARD DECISION
# ==========================================

decision = input(

    "\n[A] Admit   [R] Reject: "

).strip().upper()


if decision == "A":

    expires_at = admit_guest(
        guest_id,
        guard_name
    )

    print("\n" + "=" * 50)

    print("GUEST ADMITTED")

    print(f"\nGuest ID: {guest_id}")

    print("Status: AG — ADMITTED GUEST")

    print(
        f"Valid until: "
        f"{expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print("=" * 50)


elif decision == "R":

    reject_guest(
        guest_id,
        guard_name
    )

    print("\n" + "=" * 50)

    print("GUEST REJECTED")

    print(f"\nGuest ID: {guest_id}")

    print("Status: REJECTED")

    print("=" * 50)


else:

    print("\nInvalid decision.")