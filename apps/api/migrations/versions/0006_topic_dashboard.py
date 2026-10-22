"""topics on the dashboard: build status, added topics, pinned built-in skills

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The schema runs on PostgreSQL (the website) and SQLite (the desktop app).
JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table('topics') as batch:
        batch.add_column(sa.Column('origin', sa.String(length=20), server_default='upload', nullable=False))
        batch.add_column(sa.Column('build', JSON, nullable=True))
        batch.add_column(sa.Column('hidden', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.create_check_constraint(op.f('ck_topics_origin_valid'), "origin IN ('upload', 'added')")
    op.create_table('topic_pins',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('skill_id', sa.String(length=120), nullable=False),
    sa.Column('build', JSON, nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_topic_pins_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], name=op.f('fk_topic_pins_skill_id_skills'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'skill_id', name=op.f('pk_topic_pins'))
    )
    # Built-in skills a student already worked on, or that their uploads cover,
    # stay on their dashboard.
    op.execute("""
        INSERT INTO topic_pins (user_id, skill_id, created_at)
        SELECT user_id, skill_id, MIN(at) FROM (
            SELECT user_id, skill_id, created_at AS at FROM attempts
            UNION ALL
            SELECT lesson_progress.user_id, lessons.skill_id, lesson_progress.updated_at
            FROM lesson_progress JOIN lessons ON lessons.id = lesson_progress.lesson_id
            UNION ALL
            SELECT user_id, skill_id, created_at FROM material_problems WHERE skill_id IS NOT NULL
        ) AS activity
        WHERE skill_id NOT LIKE 'mine.%'
        GROUP BY user_id, skill_id
    """)


def downgrade() -> None:
    op.drop_table('topic_pins')
    with op.batch_alter_table('topics') as batch:
        batch.drop_constraint(op.f('ck_topics_origin_valid'), type_='check')
        batch.drop_column('hidden')
        batch.drop_column('build')
        batch.drop_column('origin')
