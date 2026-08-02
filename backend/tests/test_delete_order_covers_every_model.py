"""Every tenant-scoped model must be in _DELETE_ORDER.

This exists because six of them were not, and the way that failed was ugly out
of all proportion to the omission.

`delete_org` removes rows model by model and then deletes the Organization row
itself. Anything carrying an org_id that it forgot still references the
workspace at that point, so the final DELETE raised a foreign-key violation.
On PostgreSQL that aborts the entire transaction, and `sweep_expired` caught
the error without rolling back — so the next workspace's first SELECT failed
with "current transaction is aborted", and so did every workspace after it, on
every scheduler tick, for as long as the service stayed up.

The missing six were the Code app's version-control tables (Project,
ProjectFile, FileVersion, Commit, CommitFile, Blob), added long after
_DELETE_ORDER was written. Nothing pointed the omission out, because a list
that is merely incomplete looks exactly like one that is finished.

So the invariant is asserted rather than remembered: add a tenant-scoped model
and this test fails until the delete order knows about it.
"""
from app.core.database import Base
from app.services.tenancy import _DELETE_ORDER


def _tenant_scoped() -> set[str]:
    """Every mapped class with an org_id, except Organization itself."""
    return {
        m.class_.__name__
        for m in Base.registry.mappers
        if "org_id" in m.class_.__table__.c and m.class_.__name__ != "Organization"
    }


def test_every_tenant_scoped_model_is_deleted_with_the_workspace():
    covered = {m.__name__ for m in _DELETE_ORDER}
    missing = _tenant_scoped() - covered
    assert not missing, (
        f"{sorted(missing)} carry an org_id but are not in _DELETE_ORDER. "
        "Deleting a workspace will leave them pointing at a row that is gone, "
        "and the foreign-key violation will abort the transaction."
    )


def test_delete_order_has_no_duplicates():
    names = [m.__name__ for m in _DELETE_ORDER]
    assert len(names) == len(set(names)), "a model appears twice in _DELETE_ORDER"


def test_children_are_deleted_before_their_parents():
    """A model must not be deleted before something that references it."""
    position = {m.__name__: i for i, m in enumerate(_DELETE_ORDER)}
    by_table = {m.__tablename__: m.__name__ for m in _DELETE_ORDER}

    for model in _DELETE_ORDER:
        for col in model.__table__.c:
            for fk in col.foreign_keys:
                parent_table = fk.column.table.name
                parent = by_table.get(parent_table)
                if parent is None or parent == model.__name__:
                    continue          # not tenant-scoped, or self-referential
                assert position[model.__name__] < position[parent], (
                    f"{model.__name__}.{col.name} references {parent}, so "
                    f"{model.__name__} must be deleted first — it currently is not."
                )
