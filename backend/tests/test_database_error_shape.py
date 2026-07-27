"""What a failed request is allowed to say about why it failed.

"A database error occurred. Quote reference 7f85584033d2" is useless to
everyone who reads it. These tests hold the line between the structural facts
that make a failure diagnosable and the row values that would make the message
a leak.
"""
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.main import database_error_shape


class _PgError(Exception):
    """Stands in for psycopg2's exception, which carries the server's text."""


def _integrity(message: str) -> IntegrityError:
    return IntegrityError("INSERT INTO custom_agents ...", {}, _PgError(message))


def test_it_names_the_exception_class():
    shape = database_error_shape(_integrity("boom"))
    assert shape["cause"] == "IntegrityError"


def test_it_names_the_constraint_the_database_complained_about():
    shape = database_error_shape(_integrity(
        'duplicate key value violates unique constraint "ix_custom_agents_slug"\n'
        'DETAIL:  Key (slug)=(protocol-assistant) already exists.'))

    assert shape["database_object"] == "ix_custom_agents_slug"
    assert "duplicate key value violates unique constraint" in shape["cause_detail"]


@pytest.mark.parametrize("message,expected", [
    ('relation "dt_invoices" does not exist', "dt_invoices"),
    ('column "org_id" of relation "entities" does not exist', "entities"),
])
def test_it_names_other_kinds_of_object_too(message, expected):
    assert database_error_shape(_integrity(message))["database_object"] == expected


def test_row_values_never_survive():
    """PostgreSQL puts the offending values in DETAIL. That line is the leak."""
    shape = database_error_shape(_integrity(
        'duplicate key value violates unique constraint "ix_users_email"\n'
        'DETAIL:  Key (email)=(darshan@example.com) already exists.'))

    flat = str(shape)
    assert "darshan@example.com" not in flat
    assert "DETAIL" not in flat
    assert shape["database_object"] == "ix_users_email"      # still diagnosable


def test_a_hint_is_dropped_as_well():
    shape = database_error_shape(_integrity(
        'could not create unique index "ix_entities_key"\n'
        'HINT:  See server log for query details.'))

    assert "HINT" not in str(shape)
    assert shape["database_object"] == "ix_entities_key"


def test_an_error_that_names_nothing_still_reports_its_class():
    shape = database_error_shape(OperationalError("SELECT 1", {}, _PgError("server closed")))

    assert shape["cause"] == "OperationalError"
    assert "server closed" in shape["cause_detail"]
    assert "database_object" not in shape


def test_a_long_message_is_truncated():
    shape = database_error_shape(_integrity("x" * 5000))
    assert len(shape["cause_detail"]) <= 200


def test_it_never_raises_on_a_bare_exception():
    """This runs inside an error handler; throwing here would replace a useful
    500 with a confusing one."""
    shape = database_error_shape(Exception())
    assert shape["cause"] == "Exception"
