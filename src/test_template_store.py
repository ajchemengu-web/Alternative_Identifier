import os
import re
import shutil
import stat
import tempfile

import numpy as np

from src.services import template_store
from src.services.template_store import (
    TemplateEncryptionError,
    TemplateKeyMissingError,
)
from src import encrypt_templates


print("Testing template_store...")


def _env(keys=None, disabled=None, strict=None):

    for name, value in (
        (template_store.KEYS_ENV, keys),
        (template_store.DISABLED_ENV, disabled),
        (template_store.REQUIRE_ENCRYPTED_ENV, strict),
    ):

        if value is None:

            os.environ.pop(name, None)

        else:

            os.environ[name] = value


def _raises(exception, function, *args, **kwargs):

    try:

        function(*args, **kwargs)

    except exception as error:

        return error

    raise AssertionError(f"Expected {exception.__name__}")


temp_dir = tempfile.mkdtemp()

key_a = template_store.generate_key()
key_b = template_store.generate_key()

original = np.random.RandomState(1).rand(512).astype(np.float32)


# ------------------------------------------------------------
# ROUND TRIP + WHAT IS ON DISK
# ------------------------------------------------------------

_env(keys=key_a)

path = os.path.join(temp_dir, "STU-1.npy")

template_store.save_template(path, original)

loaded = template_store.load_template(path)

assert loaded.dtype == original.dtype and loaded.shape == original.shape
assert np.array_equal(loaded, original)
print("Round trip preserves values, dtype and shape")

raw = open(path, "rb").read()

assert template_store.is_encrypted(path)
assert b"\x93NUMPY" not in raw
assert original.tobytes()[:32] not in raw
print("Ciphertext on disk contains no .npy header and no embedding bytes")

if os.name == "posix":

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    print("Template file is owner-read/write only (0600)")

second = os.path.join(temp_dir, "STU-1b.npy")
template_store.save_template(second, original)
assert open(second, "rb").read() != raw
print("Same template, fresh nonce: ciphertexts differ")

leftovers = [n for n in os.listdir(temp_dir) if ".tmp-" in n]
assert leftovers == []
print("No temp files left behind after a write")


# ------------------------------------------------------------
# TAMPER / SWAP DETECTION
# ------------------------------------------------------------

tampered = bytearray(raw)
tampered[-1] ^= 0x01
with open(path, "wb") as handle:
    handle.write(bytes(tampered))
_raises(TemplateEncryptionError, template_store.load_template, path)
print("A flipped ciphertext bit is rejected")

with open(path, "wb") as handle:
    handle.write(raw[:-5])
_raises(TemplateEncryptionError, template_store.load_template, path)
print("A truncated file is rejected")

with open(path, "wb") as handle:
    handle.write(raw)
assert np.array_equal(template_store.load_template(path), original)

copied = os.path.join(temp_dir, "STU-2.npy")
shutil.copy(path, copied)
error = _raises(TemplateEncryptionError, template_store.load_template, copied)
assert "renamed or copied" in str(error)
print("A template copied to another person's file name is rejected")

garbage = os.path.join(temp_dir, "junk.npy")
with open(garbage, "wb") as handle:
    handle.write(b"not a template at all")
_raises(TemplateEncryptionError, template_store.load_template, garbage)
print("A file that is not a template is rejected")


# ------------------------------------------------------------
# KEYS
# ------------------------------------------------------------

_env(keys=key_b)
error = _raises(TemplateEncryptionError, template_store.load_template, path)
assert "not configured" in str(error)
print("Wrong key -> clear error, no garbage returned")

_env(keys=f"{key_b}, {key_a}")
assert np.array_equal(template_store.load_template(path), original)
print("Any listed key can decrypt (rotation window)")

for invalid in ("not base64 !!!", template_store.generate_key()[:20]):

    _env(keys=invalid)

    _raises(TemplateEncryptionError, template_store.is_enabled)

print("Malformed or wrong-length keys are rejected")


# ------------------------------------------------------------
# NO KEY / OPT-OUT / STARTUP CHECK
# ------------------------------------------------------------

_env()

unsafe = os.path.join(temp_dir, "STU-9.npy")

_raises(TemplateKeyMissingError, template_store.save_template, unsafe, original)
assert not os.path.exists(unsafe)
print("With no key, saving is refused and nothing is written")

error = _raises(RuntimeError, template_store.require_configured)
assert "generate-key" in str(error)
print("Startup check refuses to run unconfigured")

_env(disabled="1")

template_store.require_configured()
template_store.save_template(unsafe, original)
assert not template_store.is_encrypted(unsafe)
assert np.array_equal(template_store.load_template(unsafe), original)
print("Explicit opt-out stores plain text (loudly) and still works")

_env(keys=key_a)
template_store.require_configured()
print("Startup check passes with a key")


# ------------------------------------------------------------
# LEGACY PLAINTEXT + STRICT MODE
# ------------------------------------------------------------

legacy = os.path.join(temp_dir, "STU-L.npy")
np.save(legacy, original)

assert not template_store.is_encrypted(legacy)
assert np.array_equal(template_store.load_template(legacy), original)
print("A legacy plaintext template is still readable until migrated")

_env(keys=key_a, strict="1")
_raises(TemplateEncryptionError, template_store.load_template, legacy)
assert np.array_equal(template_store.load_template(path), original)
print("Strict mode refuses plaintext but reads encrypted templates")

_env(keys=key_a)


# ------------------------------------------------------------
# MIGRATION
# ------------------------------------------------------------

assert template_store.encrypt_in_place(legacy, dry_run=True) == "encrypted"
assert not template_store.is_encrypted(legacy)
print("Dry run reports but changes nothing")

assert template_store.encrypt_in_place(legacy) == "encrypted"
assert template_store.is_encrypted(legacy)
assert np.array_equal(template_store.load_template(legacy), original)
assert template_store.encrypt_in_place(legacy) == "already"
print("Migrating encrypts once and is idempotent")

_env(keys=f"{key_b},{key_a}")

assert template_store.encrypt_in_place(legacy) == "already"
assert template_store.encrypt_in_place(legacy, rotate=True, dry_run=True) == "rotated"
assert template_store.encrypt_in_place(legacy, rotate=True) == "rotated"
assert template_store.encrypt_in_place(legacy, rotate=True) == "already"

_env(keys=key_b)
assert np.array_equal(template_store.load_template(legacy), original)
print("Rotation re-keys a template; the old key is no longer needed")

_env(keys=key_a)
_raises(TemplateEncryptionError, template_store.load_template, legacy)

# If the freshly encrypted copy does not decrypt to the original, the
# original must be left alone.
fresh = os.path.join(temp_dir, "STU-V.npy")
np.save(fresh, original)
real_deserialize = template_store._deserialize
calls = []


def _lying_deserialize(payload):
    calls.append(1)
    array = real_deserialize(payload)
    return array if len(calls) == 1 else array + 1


template_store._deserialize = _lying_deserialize
try:
    _raises(TemplateEncryptionError, template_store.encrypt_in_place, fresh)
finally:
    template_store._deserialize = real_deserialize
assert not template_store.is_encrypted(fresh)
assert np.array_equal(template_store.load_template(fresh), original)
print("A failed verification leaves the original template untouched")

_env()
_raises(TemplateKeyMissingError, template_store.encrypt_in_place, legacy)
print("Migrating without a key is refused")

_env(keys=key_a)
unreadable = os.path.join(temp_dir, "STU-U.npy")
with open(unreadable, "wb") as handle:
    handle.write(b"garbage")
assert template_store.encrypt_in_place(unreadable) == "unreadable"
assert open(unreadable, "rb").read() == b"garbage"
print("An unreadable file is reported and left untouched")


# ------------------------------------------------------------
# CLI (run against a scratch data folder)
# ------------------------------------------------------------

previous_cwd = os.getcwd()
workdir = tempfile.mkdtemp()
os.chdir(workdir)

try:

    for folder in template_store.TEMPLATE_FOLDERS:

        os.makedirs(folder)

    np.save(os.path.join(template_store.TEMPLATE_FOLDERS[0], "STU-1.npy"), original)
    np.save(os.path.join(template_store.TEMPLATE_FOLDERS[2], "TGT-1.npy"), original)
    np.save(os.path.join(template_store.TEMPLATE_FOLDERS[3], "UNK-1.npy"), original)

    _env(keys=key_a)

    assert encrypt_templates._status() == {
        "encrypted": 0, "plaintext": 3, "unreadable": 0
    }
    assert encrypt_templates.main(["migrate", "--dry-run"]) == 0
    assert encrypt_templates._status()["plaintext"] == 3
    assert encrypt_templates.main(["migrate"]) == 0
    assert encrypt_templates._status() == {
        "encrypted": 3, "plaintext": 0, "unreadable": 0
    }
    assert encrypt_templates.main(["migrate"]) == 0
    assert encrypt_templates.main(["status"]) == 0
    assert encrypt_templates.main(["generate-key"]) == 0
    print("CLI: status / dry-run / migrate / re-run / generate-key behave")

    _env()
    assert encrypt_templates.main(["migrate"]) == 1
    print("CLI: migrate without a key stops with an error")

finally:

    os.chdir(previous_cwd)


# ------------------------------------------------------------
# GUARDS AGAINST BYPASS / DRIFT
# ------------------------------------------------------------

src_dir = os.path.dirname(os.path.abspath(__file__))

raw_call = re.compile(r"\bnp\.(save|load)\(")

offenders = []

for current, _dirs, files in os.walk(src_dir):

    for name in files:

        if (
            not name.endswith(".py")
            or name.startswith("test_")
            or name == "template_store.py"
        ):

            continue

        with open(os.path.join(current, name), encoding="utf-8") as handle:

            if raw_call.search(handle.read()):

                offenders.append(name)

assert offenders == [], f"Raw np.save/np.load outside template_store: {offenders}"
print("No source file bypasses template_store with np.save/np.load")

# Read the folder constants out of the sources (importing the services
# would pull in insightface).
import ast  # noqa: E402

used = set()

for current, _dirs, files in os.walk(os.path.join(src_dir, "services")):

    for name in files:

        if not name.endswith(".py") or name.startswith("test_"):

            continue

        with open(os.path.join(current, name), encoding="utf-8") as handle:

            tree = ast.parse(handle.read())

        for node in tree.body:

            if (
                isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.endswith("EMBEDDINGS_FOLDER")
            ):

                parts = [
                    arg.value for arg in node.value.args
                    if isinstance(arg, ast.Constant)
                ]

                used.add(os.path.normpath(os.path.join(*parts)))

registered = {
    os.path.normpath(folder) for folder in template_store.TEMPLATE_FOLDERS
}

assert used == registered, (
    f"TEMPLATE_FOLDERS {sorted(registered)} is out of step with the "
    f"folders the services use {sorted(used)}"
)
print("TEMPLATE_FOLDERS matches the folders the services actually use")

_env()
shutil.rmtree(temp_dir, ignore_errors=True)
shutil.rmtree(workdir, ignore_errors=True)

print("\ntemplate_store smoke test passed.")
