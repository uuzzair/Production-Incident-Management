from collections.abc import Callable
from dataclasses import dataclass
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.services.sessions import get_valid_session


@dataclass(frozen=True)
class Principal:
    actor_type: str
    subject: str
    role: str
    display_name: str | None = None
    email: str | None = None


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Principal:
    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        user_session = await get_valid_session(session, session_token, settings)
        if user_session is not None:
            user = user_session.user
            return Principal(
                actor_type="user",
                subject=user.oidc_subject,
                role=user.role,
                display_name=user.display_name,
                email=user.email,
            )

    token = request.headers.get("x-api-key")
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = None
    for configured_token, configured_role in settings.api_keys.items():
        if compare_digest(configured_token, token):
            role = configured_role
            break

    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Principal(actor_type="service", subject="api-key", role=role)


def require_roles(*allowed_roles: str) -> Callable[[Principal], Principal]:
    allowed = {role.lower() for role in allowed_roles}

    def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency
