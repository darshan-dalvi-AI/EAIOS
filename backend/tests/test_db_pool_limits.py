"""The connection pool must fit inside what the database will actually accept.

Production failure: every deploy of one service died on boot with

    FATAL: (EMAXCONNSESSION) max clients reached in session mode
           — max clients are limited to pool_size: 15
    ERROR: Application startup failed. Exiting.

The app was configured for pool_size=25 + max_overflow=60 — up to 85
connections — because those numbers were tuned by a load test that ran against
SQLite, where connection limits do not exist. Supabase's pooler allows 15.

A pool larger than the server's limit does not degrade gracefully; it refuses
the connection, and the app cannot start at all.
"""
from app.core import database

# Supabase free-tier pooler, session mode.
SERVER_LIMIT = 15

# The values the engine uses when DATABASE_URL points at Postgres. Asserted
# directly rather than through `engine.pool`, because the suite runs on SQLite
# and would otherwise be checking numbers that never reach production.
CEILING = database._pool_size + database._max_overflow


def test_pool_fits_inside_the_server_limit():
    assert CEILING <= SERVER_LIMIT, (
        f"pool can open {CEILING} connections but the server allows "
        f"{SERVER_LIMIT}; the app will fail to start")


def test_headroom_is_left_for_other_clients():
    """Migrations, a psql session and the pooler's own bookkeeping all need a
    connection. A pool sized to exactly the limit leaves none."""
    assert CEILING <= SERVER_LIMIT - 3, "leave room for migrations and admin sessions"


def test_a_full_pool_fails_fast():
    """A 30-second timeout on an exhausted pooler just queues requests behind a
    wall that is not going to move."""
    assert database.engine.pool._timeout <= 15
