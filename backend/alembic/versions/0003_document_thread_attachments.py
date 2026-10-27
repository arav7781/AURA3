"""documents attached to copilot conversations

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thread_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_documents_thread_id'), ['thread_id'], unique=False)
        batch_op.create_foreign_key('fk_documents_thread_id_copilot_threads', 'copilot_threads', ['thread_id'], ['id'],
                                    ondelete='CASCADE')


def downgrade() -> None:
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_documents_thread_id_copilot_threads', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_documents_thread_id'))
        batch_op.drop_column('thread_id')
