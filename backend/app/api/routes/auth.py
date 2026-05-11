from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import Principal, get_current_principal
from app.db.session import get_db_session
from app.services.sessions import get_valid_session, revoke_session

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/login", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def login():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OIDC login is not implemented in this phase",
    )


@router.get("/callback", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def callback():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OIDC callback is not implemented in this phase",
    )


@router.get("/me")
async def me(principal: Annotated[Principal, Depends(get_current_principal)]):
    return {
        "actor_type": principal.actor_type,
        "subject": principal.subject,
        "role": principal.role,
        "display_name": principal.display_name,
        "email": principal.email,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        user_session = await get_valid_session(session, token, settings, update_last_seen=False)
        if user_session is not None:
            await revoke_session(session, user_session)

    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    return None
