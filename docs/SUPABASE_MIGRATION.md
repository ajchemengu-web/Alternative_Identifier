# Supabase Migration

Per `docs/PRD.md` §10, production runs on Supabase/Postgres instead of the
SQLite prototype database. This is opt-in and backward compatible: with no
`DATABASE_URL` set, everything behaves exactly as before, against
`data/smarthostel.db`.

## What changed

- **`src/db.py`** is now the single place that opens a database connection.
  It returns a plain SQLite connection by default, or a Postgres connection
  (via `psycopg2`) when `DATABASE_URL` is set — wrapped so existing query
  text (`?` placeholders, `connection.row_factory = sqlite3.Row`) keeps
  working unchanged against either database.
- **`supabase/schema.sql`** is the canonical Postgres schema — apply it once
  to your Supabase project (SQL editor or `supabase db push`) before
  pointing the app at it. It mirrors `src/database.py` and the
  `src/upgrade_*.py` migrations already applied to the SQLite prototype
  (`students`, `guests`, `unknown_persons`, `access_logs`, including the
  `liveness_score` column), plus a Row Level Security placeholder — locked
  to the service role until the Enrollment Dashboard's users/roles table
  (`docs/PRD.md` §5, §8) exists to base real per-role policies on.
- The five files on the live request path were switched from
  `sqlite3.connect(...)` to `src.db.get_connection()`:
  `src/api/main.py`, `src/access_logger.py`,
  `src/services/recognition_service.py`, `src/services/guard_service.py`,
  `src/services/unknown_service.py`.

## What did not change (on purpose)

- **`src/database.py`** and every **`src/upgrade_*.py`** script remain
  SQLite-only. They bootstrap the local dev database; they are not run
  against Supabase — `supabase/schema.sql` is.
- A handful of older, standalone scripts at the top of `src/` —
  `smart_hostel_access.py`, `hostel_access.py`, `guest_manager.py`,
  `enroll_students.py`, `guard_decision.py`, `access_logs.py`,
  `view_access_logs.py` — open their own raw `sqlite3` connections and are
  not imported by anything else in the codebase (verified: nothing
  references them). They appear to predate the `src/services/` +
  `src/api/main.py` refactor and are not on the app's live request path, so
  they were left untouched rather than migrated speculatively. If any of
  them are still actively used as CLI tools, say so and they can be
  migrated too.
- Embeddings stay on disk as `.npy` files referenced by filename, not moved
  into Postgres (e.g. via `pgvector`). That's a reasonable next step once
  there's a concrete reason to query embeddings from SQL, but nothing in
  the current code needs it yet.

## Using it

1. Create a Supabase project and apply `supabase/schema.sql` to it.
2. Copy `.env.example` to `.env` and set `DATABASE_URL` to that project's
   Postgres connection string.
3. Run the app as usual — `src/db.py` picks up `DATABASE_URL` automatically
   (via `python-dotenv`) and switches from SQLite to Postgres with no other
   code changes.
