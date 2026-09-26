"""The Postgres pool shared by LangGraph's checkpointer and the app's own tables (users and chats).

A pool rather than one connection: Supabase's pooler drops connections that sit idle, and a pool
checks each connection before lending it out and reconnects, where a single connection would stay
broken until the server restarted. It also means the account queries never share a connection with
the checkpointer's writes, which run in pipeline mode.
"""
import atexit
import os

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()


def database_url() -> str:
    url = os.getenv("POSTGRES_DB")
    if not url:
        raise ValueError("POSTGRES_DB is missing.")
    return url


# Small on purpose: Supabase's free tier allows about 15 connections through its pooler in total,
# shared by the deployed app, local development and any scripts
pool = ConnectionPool(
    database_url(),
    min_size=1,
    max_size=int(os.getenv("DB_POOL_SIZE", "4")),
    # LangGraph's checkpointer needs autocommit and rows as dicts
    kwargs={"autocommit": True, "row_factory": dict_row},
    check=ConnectionPool.check_connection,
    open=True,
)

# Closed on the way out, or Python tries to stop the pool's worker thread while it's shutting down
atexit.register(pool.close)

# A user has many chats. The link lives on chats (the "many" side), and chats.thread_id is the same id
# LangGraph checkpoints the chat under, so the conversation itself is never stored twice
TABLES = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
        email         text        NOT NULL UNIQUE,
        password_hash text        NOT NULL,
        created_at    timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chats (
        thread_id  text        PRIMARY KEY,
        user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title      text        NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS chats_by_user ON chats (user_id, updated_at DESC)",
    # One row per run of the graph, which is what makes the product questions answerable: how many
    # people who start a trip get one, where they drop out, what a plan costs to serve.
    # No message text: the conversation is already in the checkpoints, and this only needs counting.
    """
    CREATE TABLE IF NOT EXISTS runs (
        id          bigserial   PRIMARY KEY,
        thread_id   text        NOT NULL,
        -- Null for guests, and set null rather than cascade when an account goes: the aggregate
        -- stays true even though the run no longer belongs to anybody
        user_id     uuid        REFERENCES users(id) ON DELETE SET NULL,
        source      text        NOT NULL,   -- message | answer | skip
        outcome     text        NOT NULL,   -- delivered | asked | refused | failed
        agents      text[]      NOT NULL DEFAULT '{}',
        llm_calls   int         NOT NULL DEFAULT 0,
        duration_ms int         NOT NULL DEFAULT 0,
        destination text,
        created_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    # A thread's runs in order: the first is the new trip, the rest are refinements
    "CREATE INDEX IF NOT EXISTS runs_by_thread ON runs (thread_id, created_at)",
    "CREATE INDEX IF NOT EXISTS runs_by_day ON runs (created_at DESC)",
    # Supabase serves every table in the public schema through its REST API. Row level security with no
    # policies closes that off; the backend connects as the tables' owner, which RLS doesn't apply to
    "ALTER TABLE users ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE chats ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE runs ENABLE ROW LEVEL SECURITY",
]


def create_tables():
    """Idempotent, so it runs on every start"""
    with pool.connection() as conn:
        for statement in TABLES:
            conn.execute(statement)


def fetch(sql: str, params=None) -> list[dict]:
    """Rows from a query, or from a write with RETURNING"""
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


def execute(sql: str, params=None) -> int:
    """A write with no rows back; returns how many rows it touched"""
    with pool.connection() as conn:
        return conn.execute(sql, params).rowcount
