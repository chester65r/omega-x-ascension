"""add account-scoped project workspaces and checkpoints

Revision ID: 9a2f3c6d7e81
Revises: 47d4a201f3c8
Create Date: 2026-10-11 14:14:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '9a2f3c6d7e81'
down_revision: Union[str, Sequence[str], None] = '47d4a201f3c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_projects_user_updated', 'projects', ['user_id', 'updated_at'], unique=False)
    op.create_table(
        'project_files',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('path', sa.String(length=512), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'path', name='uq_project_file_path'),
    )
    op.create_index('ix_project_files_project_updated', 'project_files', ['project_id', 'updated_at'], unique=False)
    op.create_table(
        'project_checkpoints',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('label', sa.String(length=80), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_project_checkpoints_project_created', 'project_checkpoints', ['project_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_project_checkpoints_project_created', table_name='project_checkpoints')
    op.drop_table('project_checkpoints')
    op.drop_index('ix_project_files_project_updated', table_name='project_files')
    op.drop_table('project_files')
    op.drop_index('ix_projects_user_updated', table_name='projects')
    op.drop_table('projects')
