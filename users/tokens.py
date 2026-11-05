"""JWT helpers for login."""

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"


class InvalidToken(Exception):
    pass


def _encode(user, token_type, lifetime):
    now = timezone.now()
    payload = {"sub": str(user.pk), "type": token_type, "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user):
    return _encode(user, ACCESS, timedelta(minutes=settings.JWT_ACCESS_TOKEN_MINUTES))


def create_refresh_token(user):
    return _encode(user, REFRESH, timedelta(days=settings.JWT_REFRESH_TOKEN_DAYS))


def decode_token(token, expected_type):
    """Returns the user id, or raises InvalidToken."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidToken(str(error)) from error

    # So a refresh token can't be used as an access token (and the other way).
    if payload["type"] != expected_type:
        raise InvalidToken("Wrong token type.")
    return int(payload["sub"])
