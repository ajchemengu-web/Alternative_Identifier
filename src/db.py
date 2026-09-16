import os
import re
import sqlite3

from dotenv import load_dotenv

load_dotenv()


# ============================================================
# WHAT THIS IS
# ============================================================
#
# A drop-in replacement for calling sqlite3.connect(DATABASE_PATH)
# directly. Every service that talks to the database (recognition,
# access, guard, unknown-person handling, the FastAPI read endpoints)
# should get its connection from here instead.
#
# - No DATABASE_URL set  -> behaves exactly like before: a plain
#   sqlite3 connection against data/smarthostel.db. This is the local
#   dev path described in docs/PRD.md §10 (SQLite stays fine for
#   running the recognition engine in isolation).
# - DATABASE_URL set      -> connects to Postgres/Supabase instead,
#   through a thin wrapper that accepts the same '?' placeholders and
#   the same `connection.row_factory = sqlite3.Row` pattern this
#   codebase already uses everywhere, so query text at each call site
#   does not need to change.
#
# What this file deliberately does NOT do: create tables. Schema
# provisioning for Postgres/Supabase lives in supabase/schema.sql,
# applied once via the Supabase SQL editor or `supabase db push` —
# src/database.py and src/upgrade_*.py remain the SQLite-only local
# dev bootstrap and are not Postgres-aware.


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

USE_POSTGRES = bool(DATABASE_URL)


if USE_POSTGRES:

    import psycopg2
    import psycopg2.extras


# A bare '?' placeholder, sqlite3-style. None of this codebase's
# query text embeds a literal '?' outside of a placeholder position,
# so a blanket substitution to Postgres's '%s' is safe.
_PLACEHOLDER = re.compile(r"\?")


def _to_postgres_placeholders(query):

    return _PLACEHOLDER.sub("%s", query)


# ============================================================
# CURSOR WRAPPER
# ============================================================

class _PostgresCursor:

    def __init__(self, raw_cursor):

        self._cursor = raw_cursor

    def execute(self, query, params=()):

        return self._cursor.execute(
            _to_postgres_placeholders(query),
            params
        )

    def executemany(self, query, seq_of_params):

        return self._cursor.executemany(
            _to_postgres_placeholders(query),
            seq_of_params
        )

    def __getattr__(self, name):

        return getattr(self._cursor, name)

    def __iter__(self):

        return iter(self._cursor)


# ============================================================
# CONNECTION WRAPPER
# ============================================================

class _PostgresConnection:

    def __init__(self, raw_connection):

        self._connection = raw_connection
        self._dict_rows = False

    # Mirrors `connection.row_factory = sqlite3.Row`, the pattern
    # every existing service already uses to get dict-style row
    # access instead of plain tuples.
    @property
    def row_factory(self):

        return sqlite3.Row if self._dict_rows else None

    @row_factory.setter
    def row_factory(self, value):

        self._dict_rows = value is not None

    def cursor(self):

        cursor_factory = (
            psycopg2.extras.RealDictCursor
            if self._dict_rows
            else None
        )

        raw_cursor = self._connection.cursor(
            cursor_factory=cursor_factory
        )

        return _PostgresCursor(raw_cursor)

    def __getattr__(self, name):

        return getattr(self._connection, name)


# ============================================================
# GET CONNECTION
# ============================================================

def get_connection():

    if USE_POSTGRES:

        return _PostgresConnection(
            psycopg2.connect(DATABASE_URL)
        )

    return sqlite3.connect(DATABASE_PATH)
