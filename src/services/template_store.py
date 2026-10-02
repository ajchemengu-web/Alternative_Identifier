import hashlib
import io
import os
import secrets
import base64

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ============================================================
# WHAT THIS IS
# ============================================================
#
# The only place face templates (embeddings) are written to or read
# from disk. Everything else calls save_template()/load_template()
# instead of np.save()/np.load(), so a template is encrypted at rest
# without each caller having to remember to — and a test
# (test_template_store.py) fails if a new caller bypasses this.
#
# Why: a face template is sensitive personal data, and docs/PRD.md §9.5
# makes encryption at rest a hard requirement. Before this, templates
# were plain .npy files, so anyone who got a copy of the data folder
# (a stolen disk, a backup, a repository) had everyone's biometrics.
#
# File format (all offsets in bytes):
#     0-3    magic  b"SGT1"
#     4-7    key id: first 4 bytes of SHA-256 of the key that encrypted it
#     8-19   random 12-byte nonce, fresh for every write
#     20-    AES-256-GCM ciphertext + 16-byte tag, of a normal .npy payload
# The magic, key id AND the file's own name are authenticated (AAD).
# Binding the name means a template can't be swapped onto another
# person by renaming or copying a file: it simply fails to decrypt.
# Consequence: never `cp`/`shutil.copy` a template to a new name —
# load_template() it and save_template() it under the new name.
#
# Keys: TEMPLATE_ENCRYPTION_KEYS is a comma-separated list of
# URL-safe-base64 32-byte keys (generate one with
# `python -m src.encrypt_templates generate-key`). The FIRST key
# encrypts new writes; every listed key can decrypt. That is the whole
# rotation story: put the new key first, keep the old one listed, run
# `python -m src.encrypt_templates migrate --rotate`, then drop the old
# key. The key lives in the environment (.env locally, the host's
# secret store in production) — never in the database or the repo.
#
# What this does NOT protect against, so nobody assumes more than it
# gives: someone who gets the running server (the key is in its memory
# and environment), someone who gets both the data AND the key, or any
# copy that already exists elsewhere (git history, old backups, SSD
# wear-levelling remnants of overwritten files). It also covers
# templates only — not the database, and not the unrecognised-visitor
# and guest photos.

MAGIC = b"SGT1"

_NPY_MAGIC = b"\x93NUMPY"

KEYS_ENV = "TEMPLATE_ENCRYPTION_KEYS"
DISABLED_ENV = "TEMPLATE_ENCRYPTION_DISABLED"
REQUIRE_ENCRYPTED_ENV = "TEMPLATE_REQUIRE_ENCRYPTED"

# Every folder that holds templates. The migration walks exactly these.
TEMPLATE_FOLDERS = [
    os.path.join("data", "embeddings"),
    os.path.join("data", "guests", "embeddings"),
    os.path.join("data", "watchlist", "embeddings"),
    os.path.join("data", "unknowns", "embeddings"),
]


class TemplateEncryptionError(Exception):

    pass


class TemplateKeyMissingError(TemplateEncryptionError):

    pass


# ============================================================
# KEYS
# ============================================================

def generate_key():

    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _parse_key(text):

    try:

        key = base64.urlsafe_b64decode(text.strip().encode())

    except Exception:

        raise TemplateEncryptionError(
            f"{KEYS_ENV} contains a value that isn't valid URL-safe base64."
        )

    if len(key) != 32:

        raise TemplateEncryptionError(
            f"{KEYS_ENV} keys must decode to exactly 32 bytes "
            f"(got {len(key)}). Generate one with "
            "`python -m src.encrypt_templates generate-key`."
        )

    return key


def _key_id(key):

    return hashlib.sha256(key).digest()[:4]


def _keyring():

    raw = os.environ.get(KEYS_ENV, "")

    keys = [
        _parse_key(part)
        for part in raw.split(",")
        if part.strip()
    ]

    return keys


def _disabled():

    return os.environ.get(DISABLED_ENV, "").strip() == "1"


def is_enabled():

    return bool(_keyring())


def require_configured():

    # Called once at server startup: refuse to run in a state where
    # templates would be written unencrypted by accident. Opting out is
    # possible but explicit (and loud).
    if is_enabled():

        return

    if _disabled():

        print(
            "[TEMPLATES] WARNING: encryption is DISABLED "
            f"({DISABLED_ENV}=1). Face templates are being stored in "
            "plain text. Do not do this with real people's data."
        )

        return

    raise RuntimeError(
        "Face template encryption is not configured. Set "
        f"{KEYS_ENV} (generate a key with "
        "`python -m src.encrypt_templates generate-key`), then encrypt "
        "any existing templates with "
        "`python -m src.encrypt_templates migrate`. For throwaway local "
        f"development only, set {DISABLED_ENV}=1 to skip encryption."
    )


# ============================================================
# ENCRYPT / DECRYPT
# ============================================================

def _aad(key_id, path):

    return MAGIC + key_id + os.path.basename(path).encode()


def _serialize(array):

    buffer = io.BytesIO()

    np.save(buffer, np.asarray(array), allow_pickle=False)

    return buffer.getvalue()


def _deserialize(payload):

    return np.load(io.BytesIO(payload), allow_pickle=False)


def _encrypt(payload, key, path):

    key_id = _key_id(key)

    nonce = secrets.token_bytes(12)

    ciphertext = AESGCM(key).encrypt(nonce, payload, _aad(key_id, path))

    return MAGIC + key_id + nonce + ciphertext


def _decrypt(blob, path):

    key_id = blob[4:8]

    nonce = blob[8:20]

    ciphertext = blob[20:]

    for key in _keyring():

        if _key_id(key) == key_id:

            try:

                return AESGCM(key).decrypt(
                    nonce, ciphertext, _aad(key_id, path)
                )

            except InvalidTag:

                raise TemplateEncryptionError(
                    f"{os.path.basename(path)} failed authentication: it "
                    "was tampered with, truncated, or has been renamed or "
                    "copied from another file."
                )

    raise TemplateEncryptionError(
        f"{os.path.basename(path)} was encrypted with a key that is not "
        f"configured (key id {key_id.hex()}). Add it to {KEYS_ENV}."
    )


def _read_bytes(path):

    with open(path, "rb") as handle:

        return handle.read()


def _write_atomic(path, data):

    # Written to a temp file and renamed into place, so a crash or a
    # full disk can never leave a half-written (undecryptable) template
    # where a good one used to be.
    temp_path = f"{path}.tmp-{secrets.token_hex(4)}"

    try:

        with open(temp_path, "wb") as handle:

            handle.write(data)

            handle.flush()

            os.fsync(handle.fileno())

        try:

            os.chmod(temp_path, 0o600)

        except OSError:

            pass

        os.replace(temp_path, path)

    except BaseException:

        if os.path.exists(temp_path):

            os.remove(temp_path)

        raise


def is_encrypted(path):

    with open(path, "rb") as handle:

        return handle.read(len(MAGIC)) == MAGIC


# ============================================================
# PUBLIC API
# ============================================================

def save_template(path, array):

    payload = _serialize(array)

    keys = _keyring()

    if keys:

        _write_atomic(path, _encrypt(payload, keys[0], path))

        return

    if _disabled():

        _write_atomic(path, payload)

        return

    # Never silently fall back to plain text: that is exactly the
    # failure this module exists to prevent.
    raise TemplateKeyMissingError(
        f"Refusing to write {os.path.basename(path)} unencrypted. Set "
        f"{KEYS_ENV} (see src/services/template_store.py)."
    )


def load_template(path):

    blob = _read_bytes(path)

    if blob.startswith(MAGIC):

        return _deserialize(_decrypt(blob, path))

    if blob.startswith(_NPY_MAGIC):

        # A template written before encryption existed. Still readable
        # so turning encryption on doesn't break a running system, until
        # `migrate` has encrypted it; strict mode refuses it.
        if os.environ.get(REQUIRE_ENCRYPTED_ENV, "").strip() == "1":

            raise TemplateEncryptionError(
                f"{os.path.basename(path)} is not encrypted and "
                f"{REQUIRE_ENCRYPTED_ENV}=1. Run "
                "`python -m src.encrypt_templates migrate`."
            )

        return _deserialize(blob)

    raise TemplateEncryptionError(
        f"{os.path.basename(path)} is not a recognised template file."
    )


# ============================================================
# MIGRATION (used by src/encrypt_templates.py)
# ============================================================

def encrypt_in_place(path, rotate=False, dry_run=False):

    """Returns "encrypted", "rotated", "already" or "unreadable".

    A plaintext template is encrypted; with rotate=True one encrypted
    under an older key is re-encrypted under the current (first) key.
    The new file is decrypted again and compared with the original
    before it replaces anything, so a bad key or a bug can't destroy a
    template.
    """

    keys = _keyring()

    if not keys:

        raise TemplateKeyMissingError(
            f"{KEYS_ENV} is not set, so there is nothing to encrypt with."
        )

    blob = _read_bytes(path)

    if blob.startswith(MAGIC):

        if not rotate or blob[4:8] == _key_id(keys[0]):

            return "already"

        try:

            array = _deserialize(_decrypt(blob, path))

        except TemplateEncryptionError:

            return "unreadable"

        outcome = "rotated"

    elif blob.startswith(_NPY_MAGIC):

        array = _deserialize(blob)

        outcome = "encrypted"

    else:

        return "unreadable"

    if dry_run:

        return outcome

    new_blob = _encrypt(_serialize(array), keys[0], path)

    check = _deserialize(_decrypt(new_blob, path))

    if not np.array_equal(check, array) or check.dtype != array.dtype:

        raise TemplateEncryptionError(
            f"Verification failed for {os.path.basename(path)}; left "
            "untouched."
        )

    _write_atomic(path, new_blob)

    return outcome
