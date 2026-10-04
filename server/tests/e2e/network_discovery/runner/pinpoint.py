"""Cookie-authenticated Pinpoint API client and bounded state polling."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
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

    def enable_plugins(self, names: list[str], evidence: list[dict[str, Any]]) -> None:
        """Enable exact inventory matches through the API and record safe state evidence."""
        plugins = []
        page = 1
        while True:
            data = self.get_data(f"/api/plugin?page={page}&per_page=100")
            if not isinstance(data, dict):
                raise HarnessError("Plugin inventory response is missing data.")
            plugins.extend(data.get("items", []))
            if page >= int(data.get("pages", 1)):
                break
            page += 1
        resolved = []
        for name in sorted(set(names)):
            matches = [item for item in plugins if item.get("name") == name]
            if len(matches) != 1:
                raise HarnessError(f"Required plugin {name} must have exactly one inventory entry.")
            resolved.append(matches[0])
        for plugin in resolved:
            record = {"id": plugin["id"], "name": plugin["name"], "before": plugin["status"]}
            evidence.append(record)
            self.request("POST", f"/api/plugin/{plugin['id']}/enable")
            details = self.get_data(f"/api/plugin/{plugin['id']}")
            record["after"] = details.get("status") if isinstance(details, dict) else None
            if record["after"] not in {"Enabled", "Active"}:
                raise HarnessError(f"Plugin {plugin['name']} did not become enabled.")

    def apply_monitoring(self, plugin_id: int, address: str, service: str) -> dict[str, Any]:
        """Apply to an existing API target and verify the running configuration."""
        targets = self.get_data("/api/plugin/targets")
        if not isinstance(targets, list):
            raise HarnessError("Monitoring targets response is missing data.")
        matches = [target for target in targets if target.get("ip_address") == address]
        if len(matches) != 1:
            raise HarnessError("Monitoring requires exactly one existing target at the lab address.")
        target_id = matches[0]["id"]
        result = self.request("POST", f"/api/plugin/{plugin_id}/configurations", {
            "net_discovery_id": target_id, "service_description": service,
        }).get("data", {})
        if result.get("success") is not True or result.get("status") != "Applied":
            raise HarnessError("Plugin monitoring configuration was not applied.")
        configurations = self.get_data(f"/api/plugin/{plugin_id}/configurations")
        applied = [item for item in configurations if item.get("id") == result.get("configuration_id")
                   and item.get("status") == "Applied" and item.get("target", {}).get("id") == target_id
                   and item.get("service_description") == service]
        if len(applied) != 1:
            raise HarnessError("Applied monitoring configuration could not be verified.")
        page = 1
        while True:
            running = self.get_data(f"/api/plugin/running?page={page}&per_page=100")
            for item in running.get("items", []):
                if (item.get("id") == result["configuration_id"]
                    and item.get("plugin", {}).get("id") == plugin_id
                    and item.get("target", {}).get("id") == target_id
                    and item.get("service_description") == service):
                    return {"configuration_id": item["id"], "target_id": target_id,
                            "hostname": item["target"]["hostname"], "service": service, "status": "Applied"}
            if page >= int(running.get("pages", 1)):
                raise HarnessError("Applied configuration is missing from running monitoring.")
            page += 1

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
        checked_after: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Wait until matching services exist and all have an expected state."""
        deadline = time.monotonic() + timeout
        expected_states = {state.upper() for state in expected_states}
        while time.monotonic() < deadline:
            matches = []
            for item in self.list_services(hostname=hostname):
                name = str(item.get("service", ""))
                if service is not None and name == service:
                    matches.append(item)
                elif service_prefix is not None and name.startswith(service_prefix):
                    matches.append(item)
            if matches and all(
                str(item.get("state", "")).upper() in expected_states
                and executed_check(item.get("last_check"), checked_after)
                for item in matches
            ):
                return matches
            time.sleep(interval)
        wanted = service or f"prefix {service_prefix}"
        raise HarnessError(f"Service {hostname}/{wanted} did not reach {sorted(expected_states)}.")


def executed_check(value: Any, checked_after: datetime | None = None) -> bool:
    """Reject pending checks and require a fresh execution after a transition."""
    try:
        if isinstance(value, (int, float)):
            checked = datetime.fromtimestamp(value, timezone.utc)
        else:
            checked = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked.timestamp() > 0 and (checked_after is None or checked > checked_after)
    except (ValueError, TypeError, OverflowError, OSError):
        return False
