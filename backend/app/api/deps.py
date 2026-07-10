from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.database import get_db, get_tenant_db
from app.models.platform import OrgMembership, Organization, User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — include 'Authorization: Bearer <token>' header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise JWTError("Missing subject claim")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_user_with_org(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Organization]:
    result = await db.execute(
        select(Organization)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(
            OrgMembership.user_id == current_user.id,
            OrgMembership.status == "active",
        )
        .limit(1)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no active organisation. Complete onboarding first.",
        )
    return current_user, org


async def require_org_admin(
    user_and_org: tuple[User, Organization] = Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Organization]:
    user, org = user_and_org
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == org.id,
            OrgMembership.status == "active",
        )
    )
    membership = result.scalar_one_or_none()
    if not membership or membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Org admin or owner role required.",
        )
    return user, org


async def require_superadmin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required.",
        )
    return current_user


@dataclass
class TenantContext:
    session: AsyncSession
    user: User
    org: Organization


async def get_tenant_context(
    user_and_org: tuple[User, Organization] = Depends(get_current_user_with_org),
) -> AsyncGenerator[TenantContext, None]:
    user, org = user_and_org
    async for session in get_tenant_db(org.slug):
        yield TenantContext(session=session, user=user, org=org)
