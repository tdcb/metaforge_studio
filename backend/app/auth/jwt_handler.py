"""JWT Issuance, Password Hashing (pwdlib/bcrypt), and Default Account Seeding."""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import bcrypt
import jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from .models import (
    Base,
    DatabaseConnectionRecord,
    ModelRevisionRecord,
    ROLE_PERMISSIONS,
    UserProfile,
    UserRecord,
    UserRole,
    engine,
)
from ..metamodel.seed import ensure_seed_workspace
from ..db_connector import ensure_demo_warehouse


def hash_password(plain_password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(
    email: str,
    role: UserRole,
    full_name: str,
    user_id: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload: Dict[str, Any] = {
        "sub": email,
        "role": role.value,
        "full_name": full_name,
        "user_id": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def build_user_profile(user: UserRecord) -> UserProfile:
    role_enum = UserRole(user.role)
    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role_enum,
        permissions=ROLE_PERMISSIONS.get(role_enum, []),
    )


DEFAULT_SEED_USERS = [
    {
        "email": "admin@metaforge.local",
        "full_name": "Elena Vance (Enterprise Admin)",
        "role": UserRole.ADMIN.value,
        "password": "password123",
    },
    {
        "email": "architect@metaforge.local",
        "full_name": "Marcus Sterling (Principal Data Architect)",
        "role": UserRole.ARCHITECT.value,
        "password": "password123",
    },
    {
        "email": "steward@metaforge.local",
        "full_name": "Priya Nair (Lead Data Governance Steward)",
        "role": UserRole.STEWARD.value,
        "password": "password123",
    },
    {
        "email": "viewer@metaforge.local",
        "full_name": "Alex Chen (Analytics Consumer / Viewer)",
        "role": UserRole.VIEWER.value,
        "password": "password123",
    },
]


def init_db_and_seed(db: Session) -> None:
    """Create SQLite tables, seed the 4 default RBAC accounts, default live DB connection, and initial v1.0.0 snapshot."""
    Base.metadata.create_all(bind=engine)

    try:
        db.execute(text("ALTER TABLE users ADD COLUMN gemini_api_key TEXT"))
        db.commit()
    except Exception:
        db.rollback()

    for acct in DEFAULT_SEED_USERS:
        existing = db.query(UserRecord).filter(UserRecord.email == acct["email"]).first()
        if not existing:
            db.add(
                UserRecord(
                    email=acct["email"],
                    full_name=acct["full_name"],
                    role=acct["role"],
                    password_hash=hash_password(acct["password"]),
                    is_active=True,
                )
            )
    db.commit()

    # Ensure Local Demo Warehouse SQLite DB exists and is registered as the default connection
    demo_db_path = settings.canonical_model_path.parent / "demo_warehouse.db"
    demo_url = ensure_demo_warehouse(demo_db_path)
    existing_conn = (
        db.query(DatabaseConnectionRecord)
        .filter(DatabaseConnectionRecord.name == "Local Demo Warehouse (SQLite Live DB)")
        .first()
    )
    if not existing_conn:
        db.add(
            DatabaseConnectionRecord(
                name="Local Demo Warehouse (SQLite Live DB)",
                dialect="sqlite",
                host="localhost",
                database_name=str(demo_db_path),
                schema_name="MAIN",
                connection_url=demo_url,
                is_default=True,
                created_by="admin@metaforge.local",
            )
        )
        db.commit()

    # Ensure initial revision exists in model_revisions
    project = ensure_seed_workspace(settings.canonical_model_path)
    first_rev = db.query(ModelRevisionRecord).first()
    if not first_rev:
        db.add(
            ModelRevisionRecord(
                revision_tag="v1.0.0-seed",
                author_email="architect@metaforge.local",
                author_role=UserRole.ARCHITECT.value,
                commit_message="Initial Enterprise Insurance & Claims baseline metamodel",
                subject_area="All",
                model_json=project.model_dump_json(indent=2),
            )
        )
        db.commit()

    # Seed Remote Model Repository & User Access Control Matrix
    from ..remote_repo import ensure_remote_repo_seeded
    ensure_remote_repo_seeded(db)


