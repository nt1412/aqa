"""add execution_reasoning.search_text + GIN FTS index

The cleaned reasoning text (embeddings.embed_text_for) is stored so keyword /
full-text retrieval can index the root-cause prose, not the raw JSON dump.

Revision ID: a7c3f1b9d2e4
Revises: bc5d4977f6e4
Create Date: 2026-06-21 11:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3f1b9d2e4"
down_revision: Union[str, Sequence[str], None] = "bc5d4977f6e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "execution_reasoning",
        sa.Column("search_text", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_execution_reasoning_search_fts",
        "execution_reasoning",
        [sa.text("to_tsvector('english', coalesce(search_text, ''))")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_execution_reasoning_search_fts", table_name="execution_reasoning")
    op.drop_column("execution_reasoning", "search_text")
