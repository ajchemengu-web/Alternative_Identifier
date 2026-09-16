-- Smart Gen / SmartAccess — Supabase (Postgres) schema
--
-- Mirrors the existing SQLite prototype schema (src/database.py plus
-- src/upgrade_unknown_persons.py, src/upgrade_unknown_embeddings.py,
-- src/upgrade_database.py, src/upgrade_liveness_logging.py,
-- src/upgrade_timetable_table.py, src/upgrade_dean_fields.py,
-- src/upgrade_cameras_table.py, src/upgrade_lecturers_table.py,
-- src/upgrade_false_positive_tracking.py, src/upgrade_semester_field.py,
-- src/upgrade_units_table.py, src/upgrade_watchlist_investigations.py,
-- src/upgrade_investigation_enhancements.py),
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
    semester integer,
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

create table if not exists units (
    id bigint generated always as identity primary key,
    unit_code text unique not null,
    unit_name text not null,
    department text,
    course text not null,
    year integer not null,
    semester integer not null,
    lecturer_id text,
    created_by text,
    created_at timestamptz not null default now()
);

create index if not exists units_lecturer_idx
    on units (lecturer_id);

create table if not exists timetable_entries (
    id bigint generated always as identity primary key,
    unit_id bigint,
    unit_code text,
    course text not null,
    year integer not null,
    department text,
    semester integer,
    lecturer_id text,
    day_of_week text not null,
    start_time text not null,
    end_time text not null,
    unit_name text not null,
    facilitator text,
    venue text not null,
    status text not null default 'ON',
    created_by text,
    created_at timestamptz not null default now()
);

create index if not exists timetable_entries_course_year_idx
    on timetable_entries (course, year, semester);

create index if not exists timetable_entries_department_idx
    on timetable_entries (department);

create index if not exists timetable_entries_lecturer_idx
    on timetable_entries (lecturer_id);

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

create table if not exists lecturers (
    id bigint generated always as identity primary key,
    lecturer_id text unique not null,
    full_name text not null,
    department text,
    created_at timestamptz not null default now()
);

-- SmartAccess "target tracking" (Security Admin dashboard). A
-- target with an embedding_file is checked by the live recognition
-- pipeline ahead of students/guests; every live sighting gets its
-- own access_logs row (person_type='TARGET') rather than being
-- cooldown-throttled like STUDENT/GUEST — see
-- src/services/watchlist_service.py and access_service.py.
create table if not exists watchlist_targets (
    id bigint generated always as identity primary key,
    target_id text unique not null,
    full_name text not null,
    description text,
    reason text,
    status text not null default 'ACTIVE',
    embedding_file text,
    linked_student_id text,
    created_by text,
    created_at timestamptz not null default now(),
    resolved_by text,
    resolved_at timestamptz
);

create index if not exists watchlist_targets_status_idx
    on watchlist_targets (status);

-- SmartAccess case management, same dashboard/role scope as the
-- watchlist above — see src/services/investigation_service.py.
-- target_id is the case's one "primary" target; investigation_targets
-- and investigation_unknowns below are link tables for everything
-- else a case can reference (more targets, unknown_persons sightings).
create table if not exists investigations (
    id bigint generated always as identity primary key,
    case_id text unique not null,
    title text not null,
    description text,
    target_id text,
    status text not null default 'OPEN',
    severity text not null default 'MEDIUM',
    assigned_to text,
    opened_by text,
    opened_at timestamptz not null default now(),
    closed_by text,
    closed_at timestamptz
);

create index if not exists investigations_status_idx
    on investigations (status);

create table if not exists investigation_notes (
    id bigint generated always as identity primary key,
    case_id text not null,
    author text,
    note text not null,
    created_at timestamptz not null default now()
);

create index if not exists investigation_notes_case_idx
    on investigation_notes (case_id);

create table if not exists investigation_targets (
    id bigint generated always as identity primary key,
    case_id text not null,
    target_id text not null,
    linked_by text,
    linked_at timestamptz not null default now()
);

create index if not exists investigation_targets_case_idx
    on investigation_targets (case_id);

create table if not exists investigation_unknowns (
    id bigint generated always as identity primary key,
    case_id text not null,
    unknown_id text not null,
    linked_by text,
    linked_at timestamptz not null default now()
);

create index if not exists investigation_unknowns_case_idx
    on investigation_unknowns (case_id);

create table if not exists access_logs (
    id bigint generated always as identity primary key,
    person_type text not null,
    person_identifier text,
    entrance text,
    recognition_score real,
    liveness_score real,
    decision text,
    guard_id text,
    false_positive boolean not null default false,
    false_positive_reason text,
    false_positive_reviewed_by text,
    false_positive_reviewed_at timestamptz,
    timestamp timestamptz not null default now(),
    alert_acknowledged boolean not null default false,
    alert_acknowledged_by text,
    alert_acknowledged_at timestamptz
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
alter table units enable row level security;
alter table timetable_entries enable row level security;
alter table cameras enable row level security;
alter table lecturers enable row level security;
alter table watchlist_targets enable row level security;
alter table investigations enable row level security;
alter table investigation_notes enable row level security;
alter table investigation_targets enable row level security;
alter table investigation_unknowns enable row level security;
