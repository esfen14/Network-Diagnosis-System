"""Cookie-authenticated Pinpoint API client and bounded state polling."""

from __future__ import annotations

import json
import time
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .common import HarnessError


class PinpointClient:
    """Minimal JSON client that preserves the Flask login session cookie."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method: str, path: str, payload: Any = None) -> dict[str, Any]:
        """Send a JSON request and return its decoded standard envelope."""
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise HarnessError(f"Pinpoint API {method} {path} returned {exc.code}: {detail}") from exc
        except URLError as exc:
            raise HarnessError(f"Cannot reach Pinpoint API at {self.base_url}: {exc.reason}") from exc
        try:
            decoded = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise HarnessError(f"Pinpoint API {path} did not return JSON.") from exc
        if not isinstance(decoded, dict) or decoded.get("success") is False:
            raise HarnessError(f"Pinpoint API {path} reported failure: {decoded}")
        return decoded

    def login(self, email: str, password: str) -> None:
        """Establish an authenticated Pinpoint session."""
        self.request("POST", "/api/user/login", {"email": email, "password": password})

    def get_data(self, path: str) -> Any:
        """Return only the data member from a standard response envelope."""
        return self.request("GET", path).get("data")

    def discovery_settings(self) -> dict[str, Any]:
        """Return current/default discovery settings and scan state."""
        data = self.get_data("/api/system/discovery-settings")
        if not isinstance(data, dict):
            raise HarnessError("Discovery Settings response is missing data.")
        return data

    def update_discovery_settings(self, desired: dict[str, Any]) -> dict[str, Any]:
        """Save a complete discovery settings payload using its current version."""
        current = self.discovery_settings()["settings"]
        payload = dict(desired)
        payload["version"] = current["version"]
        response = self.request("PUT", "/api/system/discovery-settings", payload)
        return response.get("data", {})

    def start_discovery(self) -> None:
        """Start a background Network Discovery run."""
        self.request("POST", "/api/system/discover/start")

    def discovery_status(self) -> dict[str, Any] | None:
        """Return the latest discovery status or None when none exists."""
        data = self.request("GET", "/api/system/discover/status").get("data")
        return data if isinstance(data, dict) else None

    def wait_for_discovery(self, run_id: int, timeout: int, interval: int) -> dict[str, Any]:
        """Wait for the requested discovery run to reach a terminal state."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.discovery_status()
            if status and status.get("id") == run_id and status.get("status") != "Running":
                return status
            time.sleep(interval)
        raise HarnessError(f"Discovery run {run_id} did not finish within {timeout} seconds.")

    def list_services(self, hostname: str = "", search: str = "") -> list[dict[str, Any]]:
        """Return all latest Pinpoint services matching the optional filters."""
        query = {"per_page": 100}
        if hostname:
            query["hostname"] = hostname
        if search:
            query["search"] = search
        data = self.get_data(f"/api/system/network-health/services?{urlencode(query)}")
        if not isinstance(data, dict):
            raise HarnessError("Service-list response is missing data.")
        items = list(data.get("items", []))
        for page in range(2, int(data.get("pages", 1)) + 1):
            query["page"] = page
            next_data = self.get_data(f"/api/system/network-health/services?{urlencode(query)}")
            items.extend(next_data.get("items", []))
        return items

    def wait_for_service(
        self,
        hostname: str,
        service: str | None,
        service_prefix: str | None,
        expected_states: set[str],
        timeout: int,
        interval: int,
    ) -> list[dict[str, Any]]:
        """Wait until matching services exist and all have an expected state."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            matches = []
            for item in self.list_services(hostname=hostname):
                name = str(item.get("service", ""))
                if service is not None and name == service:
                    matches.append(item)
                elif service_prefix is not None and name.startswith(service_prefix):
                    matches.append(item)
            if matches and all(str(item.get("state")) in expected_states for item in matches):
                return matches
            time.sleep(interval)
        wanted = service or f"prefix {service_prefix}"
        raise HarnessError(f"Service {hostname}/{wanted} did not reach {sorted(expected_states)}.")
