from users.models import User, Workspace

PASSWORD = "correct-horse-battery"


def make_workspace(slug="engineering", name="Engineering"):
    return Workspace.objects.create(slug=slug, name=name)


def make_user(email="employee@acme.example", role=User.Role.EMPLOYEE, workspace=None):
    workspace = workspace or Workspace.objects.get_or_create(slug="engineering", defaults={"name": "Engineering"})[0]
    return User.objects.create_user(email=email, password=PASSWORD, role=role, workspace=workspace)


def make_admin(email="admin@acme.example", workspace=None):
    return make_user(email=email, role=User.Role.ADMIN, workspace=workspace)


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}
