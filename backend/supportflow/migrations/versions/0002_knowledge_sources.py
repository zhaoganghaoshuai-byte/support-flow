"""Add source provenance to knowledge documents without rewriting existing rows."""

import sqlalchemy as sa
from alembic import op

revision = "0002_knowledge_sources"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

SOURCE_COLUMNS = {
    "source_url": 1000,
    "source_license": 200,
    "retrieved_at": 40,
    "content_hash": 64,
}


def upgrade():
    # Permit recovery after SQLite interrupted a prior ADD COLUMN, and adoption
    # of a pre-migration installation that already added these nullable fields.
    existing = (
        {}
        if op.get_context().as_sql
        else {
            column["name"]: column
            for column in sa.inspect(op.get_bind()).get_columns("knowledge_documents")
        }
    )
    for name, length in SOURCE_COLUMNS.items():
        if name in existing:
            column = existing[name]
            if (
                not isinstance(column["type"], sa.String)
                or not column["nullable"]
                or (column["type"].length is not None and column["type"].length < length)
            ):
                raise RuntimeError(
                    f"Existing knowledge metadata column {name} has an incompatible definition"
                )
            continue
        op.add_column("knowledge_documents", sa.Column(name, sa.String(length), nullable=True))


def downgrade():
    with op.batch_alter_table("knowledge_documents") as batch:
        for name in reversed(SOURCE_COLUMNS):
            batch.drop_column(name)
