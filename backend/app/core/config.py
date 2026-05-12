import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = BACKEND_DIR / "data" / "incidents.db"
DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
LOCAL_ENVIRONMENTS = {"local", "dev", "development", "test"}
DEFAULT_SESSION_SECRET = "local-session-secret-change-me"


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_api_keys(value: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for item in _split_csv(value):
        token, separator, role = item.partition(":")
        if not separator or not token.strip() or not role.strip():
            raise ValueError("API_KEYS entries must use token:role format")
        normalized_role = role.strip().lower()
        if normalized_role not in {"admin", "responder", "reporter", "readonly"}:
            raise ValueError("API key roles must be admin, responder, reporter, or readonly")
        keys[token.strip()] = normalized_role
    return keys


def _is_production_like(environment: str) -> bool:
    return environment not in LOCAL_ENVIRONMENTS


def _is_local_url(value: str | None) -> bool:
    if not value:
        return False
    host = urlparse(value).hostname
    return host in {"localhost", "127.0.0.1", "::1"}


def _is_https_url(value: str | None) -> bool:
    return bool(value and urlparse(value).scheme == "https")


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    log_level: str
    database_url: str
    cors_allowed_origins: tuple[str, ...]
    cors_allowed_origin_regex: str | None
    cors_allow_credentials: bool
    api_keys: dict[str, str]
    max_page_limit: int
    oidc_issuer_url: str | None
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_redirect_uri: str | None
    session_cookie_name: str
    session_cookie_secret: str
    session_expiry_hours: int
    csrf_cookie_name: str
    secure_cookies: bool
    oidc_state_cookie_name: str
    auth_success_redirect_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("ENVIRONMENT", "local").lower()
        database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        api_keys_value = os.getenv("API_KEYS", "local-dev-token:admin")
        cors_regex = os.getenv("CORS_ALLOWED_ORIGIN_REGEX")
        if environment == "local" and cors_regex is None:
            cors_regex = r"http://(localhost|127\.0\.0\.1):517[0-9]"

        cors_origins_configured = "CORS_ALLOWED_ORIGINS" in os.environ
        api_keys_configured = "API_KEYS" in os.environ
        session_secret_configured = "SESSION_SECRET_KEY" in os.environ or "SESSION_COOKIE_SECRET" in os.environ
        session_secret = os.getenv("SESSION_SECRET_KEY") or os.getenv("SESSION_COOKIE_SECRET", DEFAULT_SESSION_SECRET)
        secure_cookies_default = "false" if environment in LOCAL_ENVIRONMENTS else "true"

        settings = cls(
            app_name=os.getenv("APP_NAME", "Incident Management API"),
            environment=environment,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            database_url=database_url,
            cors_allowed_origins=tuple(
                _split_csv(
                    os.getenv(
                        "CORS_ALLOWED_ORIGINS",
                        "http://localhost:5173,http://127.0.0.1:5173",
                    )
                )
            ),
            cors_allowed_origin_regex=cors_regex,
            cors_allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true",
            api_keys=_parse_api_keys(api_keys_value),
            max_page_limit=int(os.getenv("MAX_PAGE_LIMIT", "100")),
            oidc_issuer_url=os.getenv("OIDC_ISSUER_URL") or None,
            oidc_client_id=os.getenv("OIDC_CLIENT_ID") or None,
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET") or None,
            oidc_redirect_uri=os.getenv("OIDC_REDIRECT_URI") or None,
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "incident_session"),
            session_cookie_secret=session_secret,
            session_expiry_hours=int(os.getenv("SESSION_EXPIRY_HOURS", "12")),
            csrf_cookie_name=os.getenv("CSRF_COOKIE_NAME", "incident_csrf"),
            secure_cookies=os.getenv("SECURE_COOKIES", secure_cookies_default).lower() == "true",
            oidc_state_cookie_name=os.getenv("OIDC_STATE_COOKIE_NAME", "incident_oidc_state"),
            auth_success_redirect_url=os.getenv(
                "AUTH_SUCCESS_REDIRECT_URL",
                os.getenv("FRONTEND_APP_URL", "http://localhost:5173"),
            ),
        )
        settings.validate(
            cors_origins_configured=cors_origins_configured,
            api_keys_configured=api_keys_configured,
            session_secret_configured=session_secret_configured,
        )
        return settings

    def validate(
        self,
        *,
        cors_origins_configured: bool,
        api_keys_configured: bool,
        session_secret_configured: bool,
    ) -> None:
        if self.max_page_limit < 1:
            raise ValueError("MAX_PAGE_LIMIT must be greater than zero")
        if self.session_expiry_hours < 1:
            raise ValueError("SESSION_EXPIRY_HOURS must be greater than zero")
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOW_CREDENTIALS cannot be true with wildcard CORS_ALLOWED_ORIGINS")

        if _is_production_like(self.environment):
            if self.database_url.startswith("sqlite+aiosqlite"):
                raise ValueError("Production must use DATABASE_URL for a non-SQLite database")
            if not api_keys_configured or "local-dev-token" in self.api_keys:
                raise ValueError("Production must set API_KEYS without the local development token")
            if not cors_origins_configured or not self.cors_allowed_origins:
                raise ValueError("Production must set CORS_ALLOWED_ORIGINS")
            if any(origin == "*" or _is_local_url(origin) or not _is_https_url(origin) for origin in self.cors_allowed_origins):
                raise ValueError("Production CORS_ALLOWED_ORIGINS must be explicit HTTPS non-local origins")
            missing_oidc = [
                name
                for name, value in {
                    "OIDC_ISSUER_URL": self.oidc_issuer_url,
                    "OIDC_CLIENT_ID": self.oidc_client_id,
                    "OIDC_CLIENT_SECRET": self.oidc_client_secret,
                    "OIDC_REDIRECT_URI": self.oidc_redirect_uri,
                }.items()
                if not value
            ]
            if missing_oidc:
                raise ValueError(f"Production auth settings missing: {', '.join(missing_oidc)}")
            if not _is_https_url(self.oidc_issuer_url) or _is_local_url(self.oidc_issuer_url):
                raise ValueError("Production must set OIDC_ISSUER_URL to an HTTPS non-local URL")
            if not _is_https_url(self.oidc_redirect_uri) or _is_local_url(self.oidc_redirect_uri):
                raise ValueError("Production must set OIDC_REDIRECT_URI to an HTTPS non-local URL")
            if not _is_https_url(self.auth_success_redirect_url) or _is_local_url(self.auth_success_redirect_url):
                raise ValueError("Production must set AUTH_SUCCESS_REDIRECT_URL to an HTTPS non-local URL")
            if (
                not session_secret_configured
                or self.session_cookie_secret == DEFAULT_SESSION_SECRET
                or len(self.session_cookie_secret) < 32
            ):
                raise ValueError("Production must set SESSION_SECRET_KEY to a strong value")
            if not self.secure_cookies:
                raise ValueError("Production must enable SECURE_COOKIES")


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
