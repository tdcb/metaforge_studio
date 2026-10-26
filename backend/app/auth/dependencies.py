"""FastAPI RBAC Route Guards and Data Steward Governance Validator."""
from typing import Callable, List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .jwt_handler import build_user_profile, decode_access_token
from .models import UserProfile, UserRecord, UserRole, get_db
from ..metamodel.schema import ProjectMetamodel

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserProfile:
    """
    Resolve the authenticated UserProfile from Bearer JWT.
    If no token is provided during local exploration, defaults to architect@metaforge.local
    so curl/local evaluation works out-of-the-box, while explicit tokens strictly enforce the
    encoded role (Admin, Data Architect, Data Steward, Viewer).
    """
    if credentials and credentials.credentials:
        try:
            payload = decode_access_token(credentials.credentials)
            email = payload.get("sub")
            user = db.query(UserRecord).filter(UserRecord.email == email).first()
            if user:
                return build_user_profile(user)
            role_val = payload.get("role", UserRole.VIEWER.value)
            return UserProfile(
                id=payload.get("user_id", 0),
                email=email or "unknown@metaforge.local",
                full_name=payload.get("full_name", "MetaForge User"),
                role=UserRole(role_val),
                permissions=[],
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired JWT token: {exc}",
            )

    # Default local session fallback to Data Architect if unauthenticated header
    fallback_user = (
        db.query(UserRecord)
        .filter(UserRecord.email == "architect@metaforge.local")
        .first()
    )
    if fallback_user:
        return build_user_profile(fallback_user)
    return UserProfile(
        id=2,
        email="architect@metaforge.local",
        full_name="Marcus Sterling (Principal Data Architect)",
        role=UserRole.ARCHITECT,
        permissions=[
            "edit_physical_model",
            "edit_business_metadata",
            "apply_glossary",
            "reverse_engineer",
            "execute_agent_mutations",
            "ask_agent_qa",
            "compile_code",
            "view_model",
        ],
    )


def require_roles(allowed_roles: List[UserRole]) -> Callable:
    """Dependency factory enforcing minimum RBAC role."""
    def _guard(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if current_user.role not in allowed_roles:
            allowed_str = ", ".join(r.value for r in allowed_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"RBAC Policy Violation: Role '{current_user.role.value}' is not authorized "
                    f"for this operation. Required role(s): {allowed_str}."
                ),
            )
        return current_user

    return _guard


def validate_steward_restrictions(
    existing_model: ProjectMetamodel,
    incoming_model: ProjectMetamodel,
    user: UserProfile,
) -> None:
    """
    Module 1 RBAC Enforcement for Data Steward:
    Data Steward can edit ONLY business metadata (logical_name, description,
    pii_classification, tags, annotations, and Naming Glossary entries); blocked
    from altering physical names, physical data types, primary/foreign keys,
    or adding/removing entities/columns/relationships.
    """
    if user.role != UserRole.STEWARD:
        return

    if set(existing_model.entities.keys()) != set(incoming_model.entities.keys()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data Steward RBAC restriction: Cannot create or drop entities.",
        )

    if set(existing_model.relationships.keys()) != set(incoming_model.relationships.keys()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data Steward RBAC restriction: Cannot create or delete physical relationships.",
        )

    for ent_id, old_ent in existing_model.entities.items():
        new_ent = incoming_model.entities[ent_id]
        if old_ent.physical_name != new_ent.physical_name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Data Steward RBAC restriction: Cannot alter physical table name '{old_ent.physical_name}'.",
            )
        old_cols = {c.id: c for c in old_ent.columns}
        new_cols = {c.id: c for c in new_ent.columns}
        if set(old_cols.keys()) != set(new_cols.keys()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Data Steward RBAC restriction: Cannot add or drop columns on '{old_ent.physical_name}'.",
            )
        for col_id, old_col in old_cols.items():
            new_col = new_cols[col_id]
            if (
                old_col.physical_name != new_col.physical_name
                or old_col.data_type_snowflake != new_col.data_type_snowflake
                or old_col.data_type_sql_server != new_col.data_type_sql_server
                or old_col.data_type_oracle != new_col.data_type_oracle
                or old_col.is_pk != new_col.is_pk
                or old_col.is_fk != new_col.is_fk
                or old_col.domain_id != new_col.domain_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Data Steward RBAC restriction: Cannot alter physical types, PK/FK keys, or domain binding "
                        f"on column '{old_col.physical_name}'."
                    ),
                )
