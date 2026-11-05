"""Role checks and the workspace filter.

Usage: @router.post("/documents", auth=IsAdmin())
"""

from ninja.errors import HttpError

from users.auth import JWTAuth
from users.models import User, Workspace


class IsEmployeeOrAdmin(JWTAuth):
    allowed_roles = {User.Role.EMPLOYEE, User.Role.ADMIN}

    def authenticate(self, request, token):
        user = super().authenticate(request, token)
        # No user = bad token (401). Wrong role = 403.
        if user is not None and user.role not in self.allowed_roles:
            raise HttpError(403, "You don't have access to this.")
        return user


class IsAdmin(IsEmployeeOrAdmin):
        allowed_roles = {User.Role.ADMIN}


def workspace_queryset(model, user):
    return model.objects.filter(workspace=user.workspace)
