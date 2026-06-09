from __future__ import annotations

import os
import secrets

ROLE_DEVELOPER = "developer"
ROLE_REVIEWER = "reviewer"


def reviewer_username() -> str:
    return os.getenv("REVIEWER_USERNAME", "treasury")


def reviewer_password() -> str:
    return os.getenv("REVIEWER_PASSWORD", "change-me-before-deploy")


def developer_username() -> str:
    return os.getenv("DEVELOPER_USERNAME", "developer")


def developer_password() -> str:
    return os.getenv("DEVELOPER_PASSWORD", "")


def session_secret() -> str:
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        return secrets.token_hex(32)
    return secret


def authenticate(username: str, password: str) -> str | None:
    dev_password = developer_password()
    if dev_password:
        if secrets.compare_digest(username, developer_username()) and secrets.compare_digest(
            password, dev_password
        ):
            return ROLE_DEVELOPER

    if secrets.compare_digest(username, reviewer_username()) and secrets.compare_digest(
        password, reviewer_password()
    ):
        return ROLE_REVIEWER

    return None


def is_authenticated(request) -> bool:
    return bool(request.session.get("authenticated"))


def get_user_role(request) -> str | None:
    if not is_authenticated(request):
        return None
    return request.session.get("role", ROLE_REVIEWER)


def has_unlimited_tests(request) -> bool:
    return get_user_role(request) == ROLE_DEVELOPER
