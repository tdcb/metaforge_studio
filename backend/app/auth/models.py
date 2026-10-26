"""SQLAlchemy 2.0 Relational Metadata, Auth, Revision History & Subject Area Lock Store."""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import settings


class UserRole(str, Enum):
    ADMIN = "Admin"
    ARCHITECT = "Data Architect"
    STEWARD = "Data Steward"
    VIEWER = "Viewer"


ROLE_PERMISSIONS: Dict[UserRole, List[str]] = {
    UserRole.ADMIN: [
        "manage_users",
        "manage_settings",
        "edit_physical_model",
        "edit_business_metadata",
        "apply_glossary",
        "reverse_engineer",
        "execute_agent_mutations",
        "ask_agent_qa",
        "compile_code",
        "view_model",
    ],
    UserRole.ARCHITECT: [
        "edit_physical_model",
        "edit_business_metadata",
        "apply_glossary",
        "reverse_engineer",
        "execute_agent_mutations",
        "ask_agent_qa",
        "compile_code",
        "view_model",
    ],
    UserRole.STEWARD: [
        "edit_business_metadata",
        "execute_agent_mutations",
        "ask_agent_qa",
        "compile_code",
        "view_model",
    ],
    UserRole.VIEWER: [
        "ask_agent_qa",
        "compile_code",
        "view_model",
    ],
}


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(64), nullable=False, default=UserRole.VIEWER.value)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    gemini_api_key = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ModelRevisionRecord(Base):
    __tablename__ = "model_revisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    revision_tag = Column(String(64), nullable=False, index=True)
    author_email = Column(String(255), nullable=False)
    author_role = Column(String(64), nullable=False)
    commit_message = Column(String(500), nullable=False)
    subject_area = Column(String(120), nullable=True)
    model_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SubjectAreaLockRecord(Base):
    __tablename__ = "subject_area_locks"

    subject_area = Column(String(120), primary_key=True)
    locked_by_email = Column(String(255), nullable=False)
    version_number = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_email = Column(String(255), nullable=False)
    actor_role = Column(String(64), nullable=False)
    action = Column(String(120), nullable=False)
    details = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DatabaseConnectionRecord(Base):
    __tablename__ = "database_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    dialect = Column(String(64), nullable=False, default="snowflake")  # sqlite, snowflake, sql_server, oracle, postgresql
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    database_name = Column(String(255), nullable=True)
    schema_name = Column(String(255), nullable=True, default="PUBLIC")
    username = Column(String(255), nullable=True)
    password_secret = Column(String(255), nullable=True)
    warehouse = Column(String(255), nullable=True)
    role_name = Column(String(255), nullable=True)
    connection_url = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    created_by = Column(String(255), nullable=False, default="admin@metaforge.local")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class RemoteModelRecord(Base):
    __tablename__ = "remote_models"

    id = Column(String(120), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    current_version = Column(Integer, default=1, nullable=False)
    version_tag = Column(String(64), default="v1.0.0", nullable=False)
    model_json = Column(Text, nullable=False)
    created_by_email = Column(String(255), nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    checked_out_by_email = Column(String(255), nullable=True)
    checked_out_by_name = Column(String(255), nullable=True)
    checked_out_at = Column(DateTime, nullable=True)
    checkout_id = Column(String(120), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class RemoteModelAccessRecord(Base):
    __tablename__ = "remote_model_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(120), index=True, nullable=False)
    user_email = Column(String(255), index=True, nullable=False)
    permission = Column(String(32), nullable=False, default="VIEW")  # NONE, VIEW, EDIT, ADMIN
    granted_by_email = Column(String(255), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class RemoteCheckoutSessionRecord(Base):
    __tablename__ = "remote_checkout_sessions"

    checkout_id = Column(String(120), primary_key=True)
    model_id = Column(String(120), index=True, nullable=False)
    user_email = Column(String(255), index=True, nullable=False)
    user_name = Column(String(255), nullable=False)
    base_version = Column(Integer, nullable=False, default=1)
    base_model_json = Column(Text, nullable=False)
    local_draft_json = Column(Text, nullable=True)
    status = Column(String(64), nullable=False, default="ACTIVE")  # ACTIVE, CHECKED_IN, RELEASED, FORCE_RELEASED, REAPPLIED
    force_released_by_email = Column(String(255), nullable=True)
    force_released_reason = Column(String(500), nullable=True)
    force_released_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# Pydantic DTOs for API responses
class UserProfile(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    permissions: List[str]


class LoginRequest(BaseModel):
    email: str
    password: str = "metaforge123"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class RevisionSummary(BaseModel):
    id: int
    revision_tag: str
    author_email: str
    author_role: str
    commit_message: str
    subject_area: Optional[str] = None
    created_at: str
    entity_count: int = 0
    relationship_count: int = 0



# Database Engine Setup
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
