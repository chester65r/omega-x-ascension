from datetime import datetime, timezone
import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default='0', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    conversations: Mapped[list['Conversation']] = relationship(back_populates='user', cascade='all, delete-orphan')


class Conversation(Base):
    __tablename__ = 'conversations'
    __table_args__ = (Index('ix_conversations_user_updated', 'user_id', 'updated_at'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default='New conversation')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    user: Mapped[User] = relationship(back_populates='conversations')
    messages: Mapped[list['Message']] = relationship(back_populates='conversation', cascade='all, delete-orphan', order_by='Message.created_at')


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        UniqueConstraint('user_id', 'client_request_id', name='uq_message_user_request'),
        Index('ix_messages_conversation_created', 'conversation_id', 'created_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    client_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    conversation: Mapped[Conversation] = relationship(back_populates='messages')


class UsageRecord(Base):
    __tablename__ = 'usage_records'
    __table_args__ = (Index('ix_usage_user_created', 'user_id', 'created_at'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class RateLimitBucket(Base):
    __tablename__ = 'auth_rate_limit_buckets'
    __table_args__ = (Index('ix_auth_rate_limit_window', 'window_start'),)

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    __table_args__ = (Index('ix_audit_events_created', 'created_at'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Project(Base):
    __tablename__ = 'projects'
    __table_args__ = (Index('ix_projects_user_updated', 'user_id', 'updated_at'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    files: Mapped[list['ProjectFile']] = relationship(back_populates='project', cascade='all, delete-orphan')
    checkpoints: Mapped[list['ProjectCheckpoint']] = relationship(back_populates='project', cascade='all, delete-orphan')


class ProjectFile(Base):
    __tablename__ = 'project_files'
    __table_args__ = (
        UniqueConstraint('project_id', 'path', name='uq_project_file_path'),
        Index('ix_project_files_project_updated', 'project_id', 'updated_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default='')
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    project: Mapped[Project] = relationship(back_populates='files')


class ProjectCheckpoint(Base):
    __tablename__ = 'project_checkpoints'
    __table_args__ = (Index('ix_project_checkpoints_project_created', 'project_id', 'created_at'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    project: Mapped[Project] = relationship(back_populates='checkpoints')
