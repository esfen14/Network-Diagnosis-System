"""Harness-owned roles and accounts for the permission matrix (names start with e2e-pdm-)."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any
from urllib.parse import quote

from .common import HarnessError
from .pinpoint import PinpointClient

PREFIX = "e2e-pdm-"


def derived_password(admin_password: str, email: str) -> str:
    """
    A password that meets the strong policy and is never stored: the API cannot change an
    existing account's password, so it is recomputed from the admin password on every run.
    """
    digest = hmac.new(admin_password.encode(), f"{PREFIX}{email}".encode(), hashlib.sha256).hexdigest()
    return f"Aa1!{digest[:28]}"


class AccountManager:
    """Create, reuse and deactivate the matrix roles and accounts through the admin API."""

    def __init__(self, admin: PinpointClient, domain: str):
        self.admin = admin
        self.domain = domain
        self.roles: dict[str, int] = {}
        self.accounts: dict[str, int] = {}

    def role_name(self, key: str) -> str:
        return f"{PREFIX}{key}"

    def email(self, key: str) -> str:
        return f"{PREFIX}{key}@{self.domain}"

    def _permission_ids(self, names: list[str]) -> list[int]:
        items = (self.admin.get_data("/api/user/permissions/options") or {}).get("items", [])
        by_name = {item["name"]: item["id"] for item in items}
        missing = [name for name in names if name not in by_name]
        if missing:
            raise HarnessError(f"Unknown permissions: {', '.join(missing)}")
        return [by_name[name] for name in names]

    def _find(self, path: str, field: str, value: str) -> dict[str, Any] | None:
        data = self.admin.get_data(f"{path}?search={quote(value)}&per_page=100") or {}
        return next((item for item in data.get("items", []) if item.get(field) == value), None)

    def ensure_role(self, key: str, permissions: list[str]) -> int:
        """Create the role or reset an existing one to exactly these permissions."""
        name = self.role_name(key)
        ids = self._permission_ids(permissions)
        existing = self._find("/api/user/roles", "name", name)
        body = {"description": f"Pinpoint e2e permission matrix ({key})", "permissions": ids, "is_active": True}
        if existing is None:
            self.admin.request("POST", "/api/user/roles", {"role_name": name, **body})
            existing = self._find("/api/user/roles", "name", name)
            if existing is None:
                raise HarnessError(f"Role {name} was not created.")
        else:
            self.admin.request("PUT", f"/api/user/roles/{existing['id']}", {"name": name, **body})
        self.roles[key] = int(existing["id"])
        return self.roles[key]

    def ensure_account(self, key: str, admin_password: str) -> int:
        """Create the account for a role or reactivate the existing one."""
        email = self.email(key)
        existing = self._find("/api/user/accounts", "email", email)
        fields = {"first_name": "E2E", "last_name": key[:20], "email": email,
                  "role_id": self.roles[key], "status": "Active"}
        if existing is None:
            password = derived_password(admin_password, email)
            self.admin.request("POST", "/api/user/accounts", {**fields, "password": password, "confirm_password": password})
            existing = self._find("/api/user/accounts", "email", email)
            if existing is None:
                raise HarnessError(f"Account {email} was not created.")
        else:
            self.admin.request("PUT", f"/api/user/accounts/{existing['id']}", fields)
        self.accounts[key] = int(existing["id"])
        return self.accounts[key]

    def set_permissions(self, key: str, permissions: list[str]) -> None:
        self.ensure_role(key, permissions)

    def deactivate(self) -> list[str]:
        """Empty each role, deactivate it and its account. Returns problems; never raises."""
        problems = []
        for key, account_id in self.accounts.items():
            try:
                self.admin.request("PUT", f"/api/user/accounts/{account_id}", {
                    "first_name": "E2E", "last_name": key[:20], "email": self.email(key),
                    "role_id": self.roles[key], "status": "Inactive"})
            except HarnessError as exc:
                problems.append(f"account {key}: {exc}")
        for key, role_id in self.roles.items():
            try:
                self.admin.request("PUT", f"/api/user/roles/{role_id}", {
                    "name": self.role_name(key), "description": f"Pinpoint e2e permission matrix ({key})",
                    "permissions": [], "is_active": False})
            except HarnessError as exc:
                problems.append(f"role {key}: {exc}")
        return problems
