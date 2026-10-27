import importlib
from io import StringIO

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from supportflow.database import make_database, make_engine
from supportflow.migration import (
    _is_active_run_predicate,
    database_revision,
    migrate_database,
    migration_config,
)
from supportflow.models import Base


def frozen_metadata():
    return importlib.import_module(
        "supportflow.migrations.versions.0001_baseline"
    ).baseline_metadata()


def insert_legacy_records(engine):
    tables = frozen_metadata().tables
    timestamp = "2026-10-27T00:00:00+00:00"
    with engine.begin() as connection:
        connection.execute(
            tables["users"]
            .insert()
            .values(
                id="person",
                email="migration@example.test",
                name="Migration User",
                role="requester",
                password_hash="test-only-not-a-credential",
                active=True,
            )
        )
        connection.execute(
            tables["conversations"]
            .insert()
            .values(
                id="conversation",
                owner_id="person",
                title="Preserve conversation",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        connection.execute(
            tables["messages"]
            .insert()
            .values(
                id="message",
                conversation_id="conversation",
                role="assistant",
                content="Preserve the answer",
                metadata_json='{"sources":[]}',
                created_at=timestamp,
            )
        )
        connection.execute(
            tables["ticket_drafts"]
            .insert()
            .values(
                id="draft",
                owner_id="person",
                conversation_id="conversation",
                title="Preserve draft",
                description="Original description",
                priority="medium",
                category="Deployment",
                status="confirmed",
                created_at=timestamp,
            )
        )
        connection.execute(
            tables["tickets"]
            .insert()
            .values(
                id="ticket",
                number="SF-MIGRATION-1",
                owner_id="person",
                draft_id="draft",
                idempotency_key="original-key",
                request_hash="original-hash",
                title="Preserve ticket",
                description="Original description",
                priority="medium",
                category="Deployment",
                status="open",
                version=1,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        connection.execute(
            tables["ticket_comments"]
            .insert()
            .values(
                id="comment",
                ticket_id="ticket",
                author_id="person",
                content="Preserve comment",
                created_at=timestamp,
            )
        )
        connection.execute(
            tables["ticket_events"]
            .insert()
            .values(
                id="event",
                ticket_id="ticket",
                actor_id="person",
                action="created",
                detail="Original event",
                created_at=timestamp,
            )
        )
        connection.execute(
            tables["agent_runs"]
            .insert()
            .values(
                id="run",
                conversation_id="conversation",
                owner_id="person",
                request_id="request-key",
                input_text="Original input",
                status="completed",
                mode="demo",
                duration_ms=10,
                tool_count=1,
                input_tokens=0,
                output_tokens=0,
                message_id="message",
                created_at=timestamp,
            )
        )
        connection.execute(
            tables["knowledge_documents"]
            .insert()
            .values(
                id="document",
                title="Preserve knowledge",
                product="FastAPI",
                version="1",
                source="Original source",
                content="Original knowledge content",
                created_by="person",
                created_at=timestamp,
            )
        )
        connection.execute(
            tables["access_sessions"]
            .insert()
            .values(token_hash="test-token-hash", user_id="person", expires_at=timestamp)
        )


def test_fresh_database_migrates_and_keeps_business_guards(tmp_path):
    engine, _ = make_database(f"sqlite:///{tmp_path / 'fresh.db'}")
    try:
        inspector = sa.inspect(engine)
        assert database_revision(engine)["revision"] == "0002_knowledge_sources"
        assert {"source_url", "source_license", "retrieved_at", "content_hash"} <= {
            column["name"] for column in inspector.get_columns("knowledge_documents")
        }
        assert "uq_conversation_active_run" in {
            index["name"] for index in inspector.get_indexes("agent_runs")
        }
        assert ("owner_id", "idempotency_key") in {
            tuple(item["column_names"]) for item in inspector.get_unique_constraints("tickets")
        }
    finally:
        engine.dispose()


def test_migrated_schema_matches_current_models(tmp_path):
    engine, _ = make_database(f"sqlite:///{tmp_path / 'model-parity.db'}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


def test_adopts_preversioned_schema_with_existing_provenance_fields(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'preversioned-current.db'}")
    Base.metadata.create_all(engine)
    insert_legacy_records(engine)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE knowledge_documents SET source_url='https://docs.example.test/original', source_license='Original license' WHERE id='document'"
            )
        )
    try:
        migrate_database(engine)
        with engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    "SELECT source_url, source_license FROM knowledge_documents WHERE id='document'"
                )
            ).one()
            assert row == ("https://docs.example.test/original", "Original license")
        assert database_revision(engine)["revision"] == "0002_knowledge_sources"
    finally:
        engine.dispose()


def test_adopts_original_create_all_database_without_losing_rows(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    frozen_metadata().create_all(engine)
    insert_legacy_records(engine)
    try:
        migrate_database(engine)
        migrate_database(engine)
        assert database_revision(engine)["revision"] == "0002_knowledge_sources"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    sa.text("SELECT content FROM messages WHERE id='message'")
                ).scalar_one()
                == "Preserve the answer"
            )
            assert (
                connection.execute(
                    sa.text("SELECT title FROM tickets WHERE id='ticket'")
                ).scalar_one()
                == "Preserve ticket"
            )
            assert (
                connection.execute(
                    sa.text("SELECT content FROM ticket_comments WHERE id='comment'")
                ).scalar_one()
                == "Preserve comment"
            )
            row = connection.execute(
                sa.text("SELECT content, source_url FROM knowledge_documents WHERE id='document'")
            ).one()
            assert row == ("Original knowledge content", None)
            assert (
                connection.execute(sa.text("SELECT count(*) FROM access_sessions")).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_partial_unversioned_schema_is_refused_without_mutation(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id TEXT PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO users VALUES ('keep-me')"))
    try:
        with pytest.raises(RuntimeError, match="incomplete"):
            migrate_database(engine)
        assert sa.inspect(engine).get_table_names() == ["users"]
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT id FROM users")).scalar_one() == "keep-me"
    finally:
        engine.dispose()


def test_legacy_schema_missing_uniqueness_guard_is_refused(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'missing-guard.db'}")
    frozen_metadata().create_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP INDEX uq_conversation_active_run"))
    try:
        with pytest.raises(RuntimeError, match="uniqueness guard"):
            migrate_database(engine)
        assert "alembic_version" not in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_metadata_upgrade_recovers_partially_added_sqlite_columns(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'partial-add.db'}")
    with engine.begin() as connection:
        command.upgrade(migration_config(connection), "0001_baseline")
        connection.execute(
            sa.text("ALTER TABLE knowledge_documents ADD COLUMN source_url VARCHAR(1000)")
        )
    try:
        migrate_database(engine)
        assert database_revision(engine)["revision"] == "0002_knowledge_sources"
        columns = [
            column["name"] for column in sa.inspect(engine).get_columns("knowledge_documents")
        ]
        assert columns.count("source_url") == 1 and "content_hash" in columns
    finally:
        engine.dispose()


def test_postgresql_migrations_can_generate_portable_ddl_without_a_server():
    output = StringIO()
    base = migration_config()
    config = Config(stdout=output, output_buffer=output)
    config.set_main_option("script_location", base.get_main_option("script_location"))
    config.set_main_option(
        "sqlalchemy.url", "postgresql+psycopg://supportflow@localhost/supportflow"
    )
    command.upgrade(config, "head", sql=True)
    ddl = output.getvalue()
    assert "CREATE TABLE tickets" in ddl
    assert "CREATE UNIQUE INDEX uq_conversation_active_run" in ddl
    assert "WHERE status = 'running'" in ddl
    assert "ADD COLUMN source_url VARCHAR(1000)" in ddl
    assert "0002_knowledge_sources" in ddl


@pytest.mark.parametrize(
    ("predicate", "valid"),
    [
        ("status = 'running'", True),
        ("((status)::text = 'running'::text)", True),
        ("(\"status\" = 'running')", True),
        ("status = 'run ning'", False),
        ("status = 'running' OR status = 'completed'", False),
        ("status = 'running' OR true", False),
    ],
)
def test_legacy_guard_validation_handles_postgres_casts_without_weakening_predicate(
    predicate, valid
):
    assert _is_active_run_predicate(predicate) is valid
