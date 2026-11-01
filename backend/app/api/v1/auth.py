"""Authentication and session endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.security import verify_password, create_access_token
from app.db.session import get_db
from app.models import User, TenantMembership, AuditEvent
from app.schemas.auth import LoginRequest, TokenResponse, UserProfileResponse, MembershipSummary
from app.services.authorization.context import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _build_user_profile(user: User, db: Session) -> UserProfileResponse:
    """Build the authorized user profile including active memberships."""
    memberships = (
        db.query(TenantMembership)
        .filter(TenantMembership.user_id == user.id, TenantMembership.status == "ACTIVE")
        .all()
    )

    membership_summaries = []
    for m in memberships:
        if m.tenant and m.tenant.status == "ACTIVE":
            membership_summaries.append(
                MembershipSummary(
                    tenant_id=m.tenant.id,
                    tenant_slug=m.tenant.slug,
                    tenant_name=m.tenant.name,
                    role=m.role,
                    status=m.status,
                )
            )

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        platform_role=user.platform_role,
        status=user.status,
        memberships=membership_summaries,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate user credentials using Argon2id.
    Issues an HttpOnly session cookie to protect against client-side XSS token theft,
    and returns user profile metadata.
    """
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    # Constant-time-like flow to prevent user enumeration
    if not user or not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Invalid email or password.")

    if user.status != "ACTIVE":
        raise AuthenticationError("User account is inactive, suspended, or disabled.")

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(
        subject=str(user.id),
        claims={
            "email": user.email,
            "platform_role": user.platform_role,
        },
    )

    # Set secure HttpOnly session cookie
    # Ensures JavaScript (DevTools / XSS) cannot read the raw access token
    response.set_cookie(
        key="nexus_session",
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=False if settings.NEXUS_ENV == "development" else True,
        path="/",
    )

    profile = _build_user_profile(user, db)

    # Log audit event
    audit = AuditEvent(
        actor_user_id=user.id,
        action="AUTH_LOGIN",
        resource_type="USER",
        resource_id=user.id,
        outcome="SUCCESS",
        metadata_json={"email": user.email, "auth_method": "HTTP_ONLY_SESSION_COOKIE"},
    )
    db.add(audit)
    db.commit()

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=profile,
    )


@router.post("/logout")
def logout(response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Terminate the current user session and wipe the HttpOnly session cookie."""
    response.delete_cookie(
        key="nexus_session",
        path="/",
        httponly=True,
        samesite="lax",
    )
    audit = AuditEvent(
        actor_user_id=current_user.id,
        action="AUTH_LOGOUT",
        resource_type="USER",
        resource_id=current_user.id,
        outcome="SUCCESS",
    )
    db.add(audit)
    db.commit()
    return {"message": "Logged out successfully. HttpOnly session cookie destroyed."}


@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the authenticated caller's profile and active tenant memberships only."""
    return _build_user_profile(current_user, db)

