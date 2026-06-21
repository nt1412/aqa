"""add execution_claims.claimant_id (doer != checker enforcement)

The agent that files a claim is recorded so verify_claim can reject a verdict
from that same identity (a different agent must confirm/refute).

Revision ID: b2d4f6a8c0e1
Revises: a7c3f1b9d2e4
Create Date: 2026-06-21 12:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, Sequence[str], None] = "a7c3f1b9d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "execution_claims",
        sa.Column("claimant_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("execution_claims", "claimant_id")
