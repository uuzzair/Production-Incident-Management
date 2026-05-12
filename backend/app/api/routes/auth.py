from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.config import get_settings
from app.core.security import Principal, ensure_csrf_token, get_current_principal, get_current_user_session
from app.db.session import get_db_session
from app.models.user import UserSession
from app.services.oidc import complete_oidc_callback, start_oidc_login, validate_oidc_claims
from app.services.sessions import get_valid_session, revoke_session, rotate_csrf_token
from app.services.sessions import create_session as create_user_session
from app.services.users import InactiveUserError, provision_oidc_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/login")
async def login(request: Request):
    return await start_oidc_login(request, get_settings())


@router.get("/callback")
async def callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    settings = get_settings()
    claims = await complete_oidc_callback(request, settings)
    validate_oidc_claims(claims)
    try:
        user = await provision_oidc_user(session, claims)
    except InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        ) from exc

    session_token, _ = await create_user_session(session, user, settings)
    response = RedirectResponse(settings.auth_success_redirect_url)
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=settings.session_expiry_hours * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me")
async def me(principal: Annotated[Principal, Depends(get_current_principal)]):
    return {
        "actor_type": principal.actor_type,
        "subject": principal.subject,
        "user_id": principal.user_id,
        "role": principal.role,
        "display_name": principal.display_name,
        "email": principal.email,
        "is_active": principal.is_active,
    }


@router.get("/csrf")
async def csrf(
    user_session: Annotated[UserSession, Depends(get_current_user_session)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return {"csrf_token": await rotate_csrf_token(session, user_session, get_settings())}


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
            ensure_csrf_token(request, user_session)
            await revoke_session(session, user_session)

    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    return None
