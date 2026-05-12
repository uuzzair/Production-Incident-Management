from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.oidc import OidcClaims
from app.services.sessions import utc_now


class InactiveUserError(Exception):
    pass


async def provision_oidc_user(session: AsyncSession, claims: OidcClaims) -> User:
    result = await session.execute(select(User).where(User.oidc_subject == claims.oidc_subject))
    user = result.scalar_one_or_none()
    now = utc_now()

    if user is None:
        user = User(
            oidc_subject=claims.oidc_subject,
            email=claims.email,
            display_name=claims.display_name,
            role="readonly",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
    else:
        if not user.is_active:
            raise InactiveUserError
        user.email = claims.email
        user.display_name = claims.display_name
        user.updated_at = now

    await session.commit()
    await session.refresh(user)
    return user
