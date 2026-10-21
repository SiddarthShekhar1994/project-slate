"""exam settings, exam answers and SM-2 skill cards

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21 05:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The schema runs on PostgreSQL (the website) and SQLite (the desktop app).
JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


OLD_STATUSES = "status IN ('up_next', 'retrying', 'cleared', 'cleared_after_retry')"
NEW_STATUSES = "status IN ('up_next', 'retrying', 'cleared', 'cleared_after_retry', 'missed')"


def upgrade() -> None:
    op.add_column('worksheets', sa.Column('settings', JSON,
                                          server_default='{}', nullable=False))
    op.add_column('worksheets', sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('worksheet_items', sa.Column('exam_answer', sa.Text(), nullable=True))
    # Batch mode: SQLite can only change a CHECK constraint by rebuilding the table.
    with op.batch_alter_table('worksheet_items') as batch:
        batch.drop_constraint(op.f('ck_worksheet_items_status_valid'), type_='check')
        batch.create_check_constraint(op.f('ck_worksheet_items_status_valid'), NEW_STATUSES)
    op.create_table('skill_cards',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('skill_id', sa.String(length=120), nullable=False),
    sa.Column('easiness', sa.Float(), nullable=False),
    sa.Column('interval_days', sa.Integer(), nullable=False),
    sa.Column('repetitions', sa.Integer(), nullable=False),
    sa.Column('lapses', sa.Integer(), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sitting', JSON, nullable=False),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], name=op.f('fk_skill_cards_skill_id_skills')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_skill_cards_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_skill_cards')),
    sa.UniqueConstraint('user_id', 'skill_id', name=op.f('uq_skill_cards_user_id'))
    )
    op.create_index(op.f('ix_skill_cards_user_id'), 'skill_cards', ['user_id'], unique=False)
    op.create_index(op.f('ix_skill_cards_due_at'), 'skill_cards', ['due_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_skill_cards_due_at'), table_name='skill_cards')
    op.drop_index(op.f('ix_skill_cards_user_id'), table_name='skill_cards')
    op.drop_table('skill_cards')
    op.execute("DELETE FROM worksheet_items WHERE status = 'missed'")
    with op.batch_alter_table('worksheet_items') as batch:
        batch.drop_constraint(op.f('ck_worksheet_items_status_valid'), type_='check')
        batch.create_check_constraint(op.f('ck_worksheet_items_status_valid'), OLD_STATUSES)
        batch.drop_column('exam_answer')
    with op.batch_alter_table('worksheets') as batch:
        batch.drop_column('ends_at')
        batch.drop_column('settings')
