"""problems and topics read from course materials

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The schema runs on PostgreSQL (the website) and SQLite (the desktop app).
JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table('sources') as batch:
        batch.add_column(sa.Column('reading', JSON, nullable=True))
    op.create_table('topics',
    sa.Column('id', sa.String(length=120), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['skills.id'], name=op.f('fk_topics_id_skills'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_topics_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_topics'))
    )
    op.create_index(op.f('ix_topics_user_id'), 'topics', ['user_id'], unique=False)
    op.create_table('material_problems',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=True),
    sa.Column('chunk_id', sa.Uuid(), nullable=True),
    sa.Column('parent_id', sa.Uuid(), nullable=True),
    sa.Column('skill_id', sa.String(length=120), nullable=True),
    sa.Column('origin', sa.String(length=20), nullable=False),
    sa.Column('label', sa.String(length=40), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('claimed', sa.Text(), nullable=False),
    sa.Column('params', JSON, nullable=False),
    sa.Column('key_latex', sa.Text(), nullable=True),
    sa.Column('answer_kind', sa.String(length=20), nullable=True),
    sa.Column('hints', JSON, nullable=False),
    sa.Column('difficulty', sa.Integer(), nullable=False),
    sa.Column('verification', JSON, nullable=False),
    sa.Column('signature', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ready', 'unchecked', 'unsupported')", name=op.f('ck_material_problems_status_valid')),
    sa.CheckConstraint("origin IN ('sheet', 'variant')", name=op.f('ck_material_problems_origin_valid')),
    sa.CheckConstraint('difficulty BETWEEN 1 AND 4', name=op.f('ck_material_problems_difficulty_range')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_material_problems_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], name=op.f('fk_material_problems_source_id_sources'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['chunk_id'], ['source_chunks.id'], name=op.f('fk_material_problems_chunk_id_source_chunks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_id'], ['material_problems.id'], name=op.f('fk_material_problems_parent_id_material_problems'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], name=op.f('fk_material_problems_skill_id_skills')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_material_problems'))
    )
    op.create_index(op.f('ix_material_problems_user_id'), 'material_problems', ['user_id'], unique=False)
    op.create_index(op.f('ix_material_problems_source_id'), 'material_problems', ['source_id'], unique=False)
    op.create_index(op.f('ix_material_problems_skill_id'), 'material_problems', ['skill_id'], unique=False)
    op.create_index(op.f('ix_material_problems_signature'), 'material_problems', ['signature'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_material_problems_signature'), table_name='material_problems')
    op.drop_index(op.f('ix_material_problems_skill_id'), table_name='material_problems')
    op.drop_index(op.f('ix_material_problems_source_id'), table_name='material_problems')
    op.drop_index(op.f('ix_material_problems_user_id'), table_name='material_problems')
    op.drop_table('material_problems')
    op.drop_index(op.f('ix_topics_user_id'), table_name='topics')
    op.drop_table('topics')
    with op.batch_alter_table('sources') as batch:
        batch.drop_column('reading')
