# Alternative_Identifier — Smart Gen Recognition Engine

FastAPI + InsightFace backend that powers **SmartAccess** (facial-recognition
checkpoint access control) for the Smart Gen platform. It resolves a face
image to a verified member, an unknown guest, or a watchlist target, and
backs the Guard, Enrollment, and Admin dashboards served by the companion
`smart-gen.com` web app.

Full product scope, roles, and decisions: [`docs/PRD.md`](docs/PRD.md).

## Tech stack

- **FastAPI** (`src/api/main.py`) — HTTP API
- **InsightFace** (`buffalo_s` model pack) + **onnxruntime** — face
  detection/embedding
- **OpenCV** (`opencv-python-headless`) — image handling
- SQLite for local dev (`data/smarthostel.db`, zero setup), **Supabase
  Postgres** for production (`DATABASE_URL`)
- **JWT** (PyJWT) session tokens, **bcrypt** password hashing

## Local setup

Requires **Python 3.11** (newer versions may not yet have installable wheels
for `insightface`/`onnxruntime` on all platforms) and **git**.

On Windows, installing `insightface`'s dependencies from source needs the
Microsoft C++ Build Tools ("Desktop development with C++" workload from
https://visualstudio.microsoft.com/visual-cpp-build-tools/) if no prebuilt
wheel is available for your Python version/platform.

```bash
git clone https://github.com/ajchemengu-web/Alternative_Identifier.git
cd Alternative_Identifier

python3.11 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt
```

### Initialize the database

`main.py` does not create the schema on startup — run these once (SQLite,
local dev):

```bash
python -m src.database
python -m src.upgrade_cameras_table
python -m src.upgrade_database
python -m src.upgrade_dean_fields
python -m src.upgrade_false_positive_tracking
python -m src.upgrade_investigation_enhancements
python -m src.upgrade_lecturers_table
python -m src.upgrade_liveness_logging
python -m src.upgrade_semester_field
python -m src.upgrade_timetable_table
python -m src.upgrade_units_table
python -m src.upgrade_unknown_embeddings
python -m src.upgrade_unknown_persons
python -m src.upgrade_users_table
python -m src.upgrade_watchlist_investigations
```

### Environment variables

Copy `.env.example` to `.env` and fill in as needed — see that file for
details on `DATABASE_URL` (defaults to local SQLite if unset) and
`JWT_SECRET` (falls back to an insecure dev-only value if unset; required
before deploying anywhere real).

### Run

```bash
uvicorn src.api.main:app --reload
```

Interactive API docs: http://127.0.0.1:8000/docs

### Tests

Smoke-test scripts (`src/test_*.py`) are plain `if __name__ == "__main__":`
scripts, not pytest-discoverable — run each as a module:

```bash
python -m src.test_recognition_service   # example
```

## Deployment

Blueprint at [`render.yaml`](render.yaml) targets Render.com, on the
`standard` plan (2GB RAM) — **Render's free tier (512MB) OOMs** loading
the InsightFace model, even on the smaller `buffalo_s` pack, so the
blueprint no longer offers that as an option. Python version is pinned via
[`.python-version`](.python-version) (Render's native Python runtime reads
this file directly — an env var does *not* control it), matching the
Python 3.11 requirement above.

To deploy: in the Render dashboard, **New → Blueprint**, connect this
repo, and it picks up `render.yaml` automatically. It'll prompt for the
two secrets marked `sync: false`:

- `DATABASE_URL` — the same Supabase Postgres connection string from
  local setup, so the deployed engine and the web dashboards read/write
  the same data instead of each running against their own SQLite file.
- `JWT_SECRET` — a real value (`openssl rand -base64 32`), not the
  insecure dev-only fallback.

Once it's live, Render gives it a stable `https://<service>.onrender.com`
URL — replace whatever `ngrok` tunnel URL is currently set as
`API_BASE_URL` in `smart-gen.com`'s Vercel project and in
`smart-attendance-app`'s `API_BASE_URL` (the GitHub Actions repo variable
for its GitHub Pages/APK builds, and the Vercel project's environment
variable for its web build) with this one. Unlike `ngrok`, it doesn't
require a tunnel process running on anyone's laptop, and doesn't change
URL every time that process restarts.

Running the engine locally/on your own hardware instead, pointed at the
same shared Supabase database via `DATABASE_URL`, remains an option too.

## Hardware

[`hardware/guard-alert-panel/`](hardware/guard-alert-panel/) — an optional
ESP32 ambient light + sound indicator for the guard post. Source code only,
not built or flashed to any device yet.
