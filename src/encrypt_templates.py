import argparse
import os
import sys

from src.services import template_store


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Operator tool for face-template encryption (see
# src/services/template_store.py for the design and its limits):
#
#   python -m src.encrypt_templates generate-key
#       Prints a new key. Put it in .env (or the host's secret store)
#       as TEMPLATE_ENCRYPTION_KEYS=<key>. Back it up somewhere safe and
#       separate from the data: lose it and every template is
#       unrecoverable (people would have to re-enrol).
#
#   python -m src.encrypt_templates migrate [--dry-run] [--rotate]
#       Encrypts every plaintext template in place. Idempotent: run it
#       again any time. --rotate also re-encrypts templates written
#       under an older key with the current (first) one.
#
#   python -m src.encrypt_templates status
#       Counts templates by state without changing anything.
#
# Run from the repository root (the data/ folders are relative paths),
# against the same data folder the server uses.


def _templates():

    for folder in template_store.TEMPLATE_FOLDERS:

        if not os.path.isdir(folder):

            continue

        for name in sorted(os.listdir(folder)):

            if name.endswith(".npy"):

                yield os.path.join(folder, name)


def _status():

    counts = {"encrypted": 0, "plaintext": 0, "unreadable": 0}

    for path in _templates():

        try:

            counts["encrypted" if template_store.is_encrypted(path)
                   else "plaintext"] += 1

        except OSError:

            counts["unreadable"] += 1

    return counts


def main(argv=None):

    parser = argparse.ArgumentParser(prog="python -m src.encrypt_templates")

    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("generate-key")

    commands.add_parser("status")

    migrate = commands.add_parser("migrate")

    migrate.add_argument("--dry-run", action="store_true")

    migrate.add_argument("--rotate", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "generate-key":

        print(template_store.generate_key())

        return 0

    if args.command == "status":

        counts = _status()

        print(
            f"encrypted: {counts['encrypted']}  "
            f"plaintext: {counts['plaintext']}  "
            f"unreadable: {counts['unreadable']}"
        )

        return 0

    results = {"encrypted": 0, "rotated": 0, "already": 0, "unreadable": 0}

    try:

        for path in _templates():

            outcome = template_store.encrypt_in_place(
                path,
                rotate=args.rotate,
                dry_run=args.dry_run
            )

            results[outcome] += 1

            if outcome == "unreadable":

                print(f"  could not read {path}")

    except template_store.TemplateEncryptionError as error:

        print(f"Stopped: {error}")

        return 1

    label = "would be " if args.dry_run else ""

    print(
        f"{label}encrypted: {results['encrypted']}  "
        f"{label}re-keyed: {results['rotated']}  "
        f"already current: {results['already']}  "
        f"unreadable: {results['unreadable']}"
    )

    if not args.dry_run and results["encrypted"]:

        print(
            "Overwritten files can survive in backups, git history and "
            "disk remnants — see docs/DPIA.md."
        )

    return 1 if results["unreadable"] else 0


if __name__ == "__main__":

    sys.exit(main())
