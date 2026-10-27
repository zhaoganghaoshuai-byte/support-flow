"""Safe upgrades for new databases and validated pre-Alembic installations."""

import importlib
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Boolean, Integer, String, Text, inspect

BASELINE_REVISION = "0001_baseline"


def migration_config(connection=None):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _compatible_type(actual, expected):
    if isinstance(expected, Boolean):
        return isinstance(actual, Boolean)
    if isinstance(expected, Integer):
        return isinstance(actual, Integer)
    if isinstance(expected, Text):
        return isinstance(actual, Text)
    if isinstance(expected, String):
        return isinstance(actual, String) and (
            actual.length is None or actual.length >= expected.length
        )
    return actual._type_affinity is expected._type_affinity


def _is_active_run_predicate(predicate):
    # PostgreSQL reflects VARCHAR comparisons with harmless ::text casts.
    # Check string literals before whitespace normalization so 'run ning' can
    # never be mistaken for the actual running-state predicate.
    if re.findall(r"'(?:''|[^'])*'", predicate) != ["'running'"]:
        return False
    normalized = "".join(
        predicate.lower().replace('"', "").replace("(", "").replace(")", "").split()
    )
    normalized = normalized.replace("::text", "").replace("::charactervarying", "")
    return normalized == "status='running'"


def validate_legacy_schema(connection):
    """Only stamp a complete compatible historical schema, never a partial DB."""
    frozen = importlib.import_module(
        "supportflow.migrations.versions.0001_baseline"
    ).baseline_metadata()
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing = set(frozen.tables) - tables
    if missing:
        raise RuntimeError(
            "Unversioned database is incomplete; back it up and inspect missing tables: "
            + ", ".join(sorted(missing))
        )
    for table in frozen.sorted_tables:
        actual = {column["name"]: column for column in inspector.get_columns(table.name)}
        for expected in table.columns:
            column = actual.get(expected.name)
            if (
                column is None
                or not _compatible_type(column["type"], expected.type)
                or bool(column["nullable"]) != bool(expected.nullable)
            ):
                raise RuntimeError(
                    f"Unversioned database has an incompatible column: {table.name}.{expected.name}"
                )
        primary = inspector.get_pk_constraint(table.name).get("constrained_columns", [])
        if tuple(primary) != tuple(column.name for column in table.primary_key):
            raise RuntimeError(
                f"Unversioned database has an incompatible primary key: {table.name}"
            )
        unique_sets = {
            tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name)
        }
        unique_sets.update(
            tuple(item["column_names"])
            for item in inspector.get_indexes(table.name)
            if item.get("unique") and not item.get("dialect_options")
        )
        for constraint in table.constraints:
            if (
                constraint.__class__.__name__ == "UniqueConstraint"
                and tuple(column.name for column in constraint.columns) not in unique_sets
            ):
                raise RuntimeError(
                    f"Unversioned database is missing a uniqueness constraint: {table.name}"
                )
        actual_foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
            )
            for item in inspector.get_foreign_keys(table.name)
        }
        for constraint in table.foreign_key_constraints:
            key = (
                tuple(element.parent.name for element in constraint.elements),
                constraint.referred_table.name,
                tuple(element.column.name for element in constraint.elements),
            )
            if key not in actual_foreign_keys:
                raise RuntimeError(f"Unversioned database is missing a foreign key: {table.name}")
    active = next(
        (
            item
            for item in inspector.get_indexes("agent_runs")
            if item["name"] == "uq_conversation_active_run"
        ),
        None,
    )
    predicate = (
        ""
        if not active
        else str(active.get("dialect_options", {}).get(connection.dialect.name + "_where", ""))
    )
    if (
        not active
        or not active.get("unique")
        or active["column_names"] != ["conversation_id"]
        or not _is_active_run_predicate(predicate)
    ):
        raise RuntimeError(
            "Unversioned database is missing the active conversation run uniqueness guard"
        )


def migrate_database(engine):
    with engine.begin() as connection:
        config = migration_config(connection)
        tables = set(inspect(connection).get_table_names())
        version = MigrationContext.configure(connection).get_current_revision()
        if version is None and tables - {"alembic_version"}:
            validate_legacy_schema(connection)
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")


def database_revision(engine):
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return {
        "dialect": engine.dialect.name,
        "revision": current,
        "head": ScriptDirectory.from_config(migration_config()).get_current_head(),
    }
