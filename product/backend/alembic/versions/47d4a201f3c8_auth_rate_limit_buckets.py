"""add hashed authentication rate limits and pseudonymous audit events

Revision ID: 47d4a201f3c8
Revises: 06bf1418b5cb
Create Date: 2026-10-11 14:02:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '47d4a201f3c8'
down_revision: Union[str, Sequence[str], None] = '06bf1418b5cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'auth_rate_limit_buckets',
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('window_start', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('key_hash', 'window_start'),
    )
    op.create_index('ix_auth_rate_limit_window', 'auth_rate_limit_buckets', ['window_start'], unique=False)
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('subject_hash', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_events_created', 'audit_events', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_audit_events_created', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('ix_auth_rate_limit_window', table_name='auth_rate_limit_buckets')
    op.drop_table('auth_rate_limit_buckets')
