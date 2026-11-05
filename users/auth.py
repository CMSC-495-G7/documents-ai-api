"""Default auth for the API, set in config/api.py."""

from ninja.security import HttpBearer

from users.models import User
from users.tokens import ACCESS, InvalidToken, decode_token


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            user_id = decode_token(token, ACCESS)
        except InvalidToken:
            return None

        # None = 401, otherwise this becomes request.auth.
        return User.objects.select_related("workspace").filter(pk=user_id, is_active=True).first()
