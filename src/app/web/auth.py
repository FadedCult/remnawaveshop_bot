from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from starlette.requests import Request

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
COOKIE_NAME = "admin_session"


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.session_secret, salt="remnashop-admin")


def create_session_token(login: str) -> str:
    return _serializer().dumps({"login": login})


def read_session_token(token: str, max_age_seconds: int = 60 * 60 * 12) -> str | None:
    try:
        data = _serializer().loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("login")


def verify_password(password: str) -> bool:
    settings = get_settings()
    if settings.admin_password_hash:
        return pwd_context.verify(password, settings.admin_password_hash)
    return password == settings.admin_password


def is_authorized(request: Request) -> tuple[bool, str | None]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False, None
    login = read_session_token(token)
    if not login:
        return False, None
    return True, login


def hash_password(raw_password: str) -> str:
    return pwd_context.hash(raw_password)

