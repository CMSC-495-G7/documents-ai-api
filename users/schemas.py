from ninja import Schema


class ErrorOut(Schema):
    detail: str


class LoginIn(Schema):
    email: str
    password: str


class RefreshIn(Schema):
    refresh: str


class TokenPairOut(Schema):
    access: str
    refresh: str


class AccessTokenOut(Schema):
    access: str


class WorkspaceOut(Schema):
    id: int
    name: str
    slug: str


class MeOut(Schema):
    id: int
    email: str
    role: str
    workspace: WorkspaceOut
