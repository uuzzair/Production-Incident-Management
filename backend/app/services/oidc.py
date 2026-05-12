import secrets
from dataclasses import dataclass
from typing import Any

from authlib.integrations.base_client.errors import OAuthError
from fastapi import HTTPException, Request, status
from starlette.responses import Response

from app.core.config import Settings


@dataclass(frozen=True)
class OidcClaims:
    oidc_subject: str
    email: str
    display_name: str | None


def require_oidc_settings(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "OIDC_ISSUER_URL": settings.oidc_issuer_url,
            "OIDC_CLIENT_ID": settings.oidc_client_id,
            "OIDC_CLIENT_SECRET": settings.oidc_client_secret,
            "OIDC_REDIRECT_URI": settings.oidc_redirect_uri,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OIDC auth is not configured: {', '.join(missing)}",
        )


def get_oidc_client(settings: Settings):
    from authlib.integrations.starlette_client import OAuth

    require_oidc_settings(settings)
    oauth = OAuth()
    issuer = settings.oidc_issuer_url.rstrip("/") if settings.oidc_issuer_url else ""
    oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{issuer}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.oidc


async def start_oidc_login(request: Request, settings: Settings) -> Response:
    client = get_oidc_client(settings)
    nonce = secrets.token_urlsafe(24)
    return await client.authorize_redirect(
        request,
        settings.oidc_redirect_uri,
        nonce=nonce,
    )


async def complete_oidc_callback(request: Request, settings: Settings) -> OidcClaims:
    client = get_oidc_client(settings)
    try:
        token = await client.authorize_access_token(request)
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC callback validation failed",
        ) from exc

    if not token.get("id_token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC provider did not return an ID token",
        )

    try:
        raw_claims = await client.parse_id_token(request, token)
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC ID token validation failed",
        ) from exc

    if raw_claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC provider did not return user claims",
        )
    return extract_oidc_claims(raw_claims)


def extract_oidc_claims(raw_claims: dict[str, Any]) -> OidcClaims:
    subject = str(raw_claims.get("sub") or "").strip()
    email = str(raw_claims.get("email") or "").strip().lower()
    display_name = (
        str(raw_claims.get("name") or raw_claims.get("preferred_username") or "").strip()
        or None
    )
    claims = OidcClaims(
        oidc_subject=subject,
        email=email,
        display_name=display_name,
    )
    validate_oidc_claims(claims)
    return claims


def validate_oidc_claims(claims: OidcClaims) -> None:
    if not claims.oidc_subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC subject is required",
        )
    if not claims.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC email is required",
        )
