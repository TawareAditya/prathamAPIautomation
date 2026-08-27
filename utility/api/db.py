"""Read-only PostgreSQL access to the QA `pratham` database.

Used to verify that what the API *reports* actually matches what was *stored* —
the API has been caught returning success while silently discarding data
(see ATM-91), which only a direct DB read can catch.

Configuration comes entirely from environment variables so no credentials live
in the repository:

    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DATABASE,
    POSTGRES_USERNAME, POSTGRES_PASSWORD

If any are missing, is_configured() returns False and the DB tests skip. The
connection is opened read-only; this module only ever issues SELECTs.
"""

import os
import socket
from contextlib import contextmanager
from functools import lru_cache

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # driver optional — DB tests skip without it
    psycopg2 = None

REQUIRED_VARS = (
    "POSTGRES_HOST",
    "POSTGRES_DATABASE",
    "POSTGRES_USERNAME",
    "POSTGRES_PASSWORD",
)


def is_configured():
    return psycopg2 is not None and all(os.getenv(v) for v in REQUIRED_VARS)


def missing_reason():
    if psycopg2 is None:
        return "psycopg2 not installed"
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    return f"DB env not set: {', '.join(missing)}" if missing else ""


@lru_cache(maxsize=1)
def reachable(timeout=3.0):
    """Fast one-time TCP check for the DB host:port.

    Cached for the whole session so an unreachable DB (e.g. from a CI runner
    the firewall blocks) costs one short check, not a full connect timeout on
    every test.
    """
    host = os.getenv("POSTGRES_HOST")
    if not host:
        return False
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


@contextmanager
def connection():
    """A read-only, autocommit connection. Read-only is enforced at the
    session level so a bug in a query can never write."""
    conn = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DATABASE"],
        user=os.environ["POSTGRES_USERNAME"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=int(os.getenv("POSTGRES_TIMEOUT", "10")),
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        yield conn
    finally:
        conn.close()


def _one(conn, sql, args):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def _all(conn, sql, args):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def get_user(conn, user_id):
    """The Users row for a userId, or None."""
    return _one(
        conn,
        'select "userId","username","firstName","lastName","mobile","gender",'
        '"dob","status","enrollmentId" from "Users" where "userId"=%s',
        (user_id,),
    )


def get_tenant_mappings(conn, user_id):
    """Tenant memberships for a user: [{tenantName, status}]."""
    return _all(
        conn,
        'select t."name" as "tenantName", utm."status" '
        'from "UserTenantMapping" utm '
        'join "Tenants" t on t."tenantId"=utm."tenantId" '
        'where utm."userId"=%s',
        (user_id,),
    )


def get_field_values(conn, user_id):
    """Custom field values stored for a user: {fieldId: raw_value}."""
    rows = _all(
        conn,
        'select fv."fieldId", f."label", fv."value" '
        'from "FieldValues" fv join "Fields" f on f."fieldId"=fv."fieldId" '
        'where fv."itemId"=%s',
        (user_id,),
    )
    return {r["fieldId"]: r for r in rows}
