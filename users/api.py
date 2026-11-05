from django.contrib.auth import authenticate
from ninja import Router
from ninja.errors import HttpError

from users.models import User
from users.schemas import AccessTokenOut, ErrorOut, LoginIn, MeOut, RefreshIn, TokenPairOut
from users.tokens import REFRESH, InvalidToken, create_access_token, create_refresh_token, decode_token

router = Router(tags=["Auth"])


@router.post("/login", auth=None, response={200: TokenPairOut, 401: ErrorOut})
def login(request, payload: LoginIn):
    user = authenticate(request, email=payload.email.strip().lower(), password=payload.password)
    if user is None:
        # Same message for both so you can't tell which emails exist.
        raise HttpError(401, "Incorrect email or password.")
    return {"access": create_access_token(user), "refresh": create_refresh_token(user)}


@router.post("/refresh", auth=None, response={200: AccessTokenOut, 401: ErrorOut})
def refresh(request, payload: RefreshIn):
    # Bad/expired token or inactive user -> 401.
    try:
        user_id = decode_token(payload.refresh, REFRESH)
    except InvalidToken:
        raise HttpError(401, "Your session has expired. Sign in again.")

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise HttpError(401, "Your session has expired. Sign in again.")
    return {"access": create_access_token(user)}


@router.get("/me", response=MeOut)
def me(request):
    # JWTAuth already loaded the user.
    return request.auth
