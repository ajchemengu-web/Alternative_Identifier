-- Smart Gen / SmartAccess — Supabase (Postgres) schema
--
-- Mirrors the existing SQLite prototype schema (src/database.py plus
-- src/upgrade_unknown_persons.py, src/upgrade_unknown_embeddings.py,
-- src/upgrade_database.py, src/upgrade_liveness_logging.py,
-- src/upgrade_timetable_table.py, src/upgrade_dean_fields.py,
-- src/upgrade_cameras_table.py),
-- translated to Postgres syntax, for docs/PRD.md §10's move off
-- SQLite for production.
--
-- Apply this once via the Supabase SQL editor or `supabase db push`.
-- The app's own src/database.py and src/upgrade_*.py scripts are the
-- SQLite bootstrap for local dev only — they do not run this file,
-- and this file does not run them. Once applied, point the app at
-- Supabase by setting DATABASE_URL (see .env.example); src/db.py
-- picks it up automatically.

create table if not exists students (
    id bigint generated always as identity primary key,
    student_id text unique not null,
    full_name text not null,
    admission_number text unique not null,
    hostel text not null,
    room text not null,
    department text,
    course text,
    year integer,
    embedding_file text not null,
    created_at timestamptz not null default now()
);

create index if not exists students_department_idx
    on students (department);

create table if not exists guests (
    id bigint generated always as identity primary key,
    guest_id text unique not null,
    photo_path text,
    embedding_file text,
    status text not null,
    admitted_by text,
    admitted_at timestamptz,
    rejected_by text,
    rejected_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists unknown_persons (
    id bigint generated always as identity primary key,
    unknown_id text unique not null,
    image_path text not null,
    embedding_file text,
    status text not null default 'PENDING_REVIEW',
    detected_at timestamptz not null default now(),
    reviewed_at timestamptz,
    reviewed_by text
);

create table if not exists users (
    id bigint generated always as identity primary key,
    username text unique not null,
    password_hash text not null,
    email text unique not null,
    role text not null,
    admin_tier text,
    linked_person_id text,
    temp_expires_at timestamptz,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists timetable_entries (
    id bigint generated always as identity primary key,
    course text not null,
    year integer not null,
    department text,
    day_of_week text not null,
    start_time text not null,
    end_time text not null,
    unit_name text not null,
    facilitator text not null,
    venue text not null,
    status text not null default 'ON',
    created_by text,
    created_at timestamptz not null default now()
);

create index if not exists timetable_entries_course_year_idx
    on timetable_entries (course, year);

create index if not exists timetable_entries_department_idx
    on timetable_entries (department);

create table if not exists cameras (
    id bigint generated always as identity primary key,
    camera_id text unique not null,
    name text not null,
    camera_type text not null,
    location text,
    department text,
    source text,
    status text not null default 'OFFLINE',
    enabled boolean not null default true,
    created_by text,
    created_at timestamptz not null default now()
);

create index if not exists cameras_type_idx
    on cameras (camera_type);

create index if not exists cameras_department_idx
    on cameras (department);

create table if not exists access_logs (
    id bigint generated always as identity primary key,
    person_type text not null,
    person_identifier text,
    entrance text,
    recognition_score real,
    liveness_score real,
    decision text,
    guard_id text,
    timestamp timestamptz not null default now()
);

create index if not exists access_logs_timestamp_idx on access_logs (timestamp desc);
create index if not exists guests_status_idx on guests (status);
create index if not exists unknown_persons_status_idx on unknown_persons (status);


-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
--
-- The `users` table backs request-level auth on the FastAPI side
-- (a Bearer JWT per user, checked in src/api/deps.py) rather than
-- Postgres-level roles, so these tables stay locked down to the
-- service role only: the FastAPI backend connects with the Supabase
-- service key, which bypasses RLS, while every other role (anon,
-- authenticated) is denied by default once RLS is enabled and no
-- policy grants access.

alter table students enable row level security;
alter table guests enable row level security;
alter table unknown_persons enable row level security;
alter table access_logs enable row level security;
alter table users enable row level security;
alter table timetable_entries enable row level security;
alter table cameras enable row level security;
