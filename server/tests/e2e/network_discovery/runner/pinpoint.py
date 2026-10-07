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

from .common import BlockedError, HarnessError


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

    def call(self, method: str, path: str, payload: Any = None) -> tuple[int, Any]:
        """
        Send a request and return (HTTP status, decoded JSON) without raising on
        a 4xx/5xx reply, so permission and rejection cases can assert the status.
        Only an unreachable server raises.
        """
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                status, body = response.status, response.read().decode("utf-8")
        except HTTPError as exc:
            status, body = exc.code, exc.read().decode("utf-8", errors="replace")
        except URLError as exc:
            raise HarnessError(f"Cannot reach Pinpoint API at {self.base_url}: {exc.reason}") from exc
        try:
            return status, (json.loads(body) if body else {})
        except json.JSONDecodeError:
            return status, {}

    def plugin_by_name(self, name: str) -> dict[str, Any]:
        """Return the single inventory entry for an exact plugin name."""
        page = 1
        while True:
            data = self.get_data(f"/api/plugin?page={page}&per_page=100")
            if not isinstance(data, dict):
                raise HarnessError("Plugin inventory response is missing data.")
            for item in data.get("items", []):
                if item.get("name") == name:
                    return item
            if page >= int(data.get("pages", 1)):
                raise HarnessError(f"Required plugin {name} must have exactly one inventory entry.")
            page += 1

    def enable_preview(self, plugin_id: int) -> dict[str, Any]:
        """Return what enabling would monitor, without changing anything."""
        data = self.get_data(f"/api/plugin/{plugin_id}/enable-preview")
        if not isinstance(data, dict):
            raise HarnessError("Enable preview response is missing data.")
        return data

    def enable_plugin(self, plugin_id: int) -> dict[str, Any]:
        """Enable one plugin; the response carries auto_apply with the Nagios outcome."""
        data = self.request("POST", f"/api/plugin/{plugin_id}/enable").get("data")
        return data if isinstance(data, dict) else {}

    def disable_plugin(self, plugin_id: int) -> dict[str, Any]:
        """Disable one plugin; a Nagios rejection raises HarnessError (502)."""
        data = self.request("POST", f"/api/plugin/{plugin_id}/disable").get("data")
        return data if isinstance(data, dict) else {}

    def plugin_services(self, plugin_id: int, search: str = "") -> list[dict[str, Any]]:
        """Return every service a plugin monitors, across all pages."""
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            query = {"page": page, "per_page": 100}
            if search:
                query["search"] = search
            data = self.get_data(f"/api/plugin/{plugin_id}/services?{urlencode(query)}")
            if not isinstance(data, dict):
                raise HarnessError("Plugin services response is missing data.")
            items.extend(data.get("items", []))
            if page >= int(data.get("pages", 1)):
                return items
            page += 1

    def stop_service(self, plugin_id: int, device_id: int, protocol: str, port: int) -> dict[str, Any]:
        """Stop monitoring one port on one device through its plugin."""
        body = {"device_id": device_id, "protocol": protocol, "port": port}
        data = self.request("POST", f"/api/plugin/{plugin_id}/services/stop", body).get("data")
        return data if isinstance(data, dict) else {}

    def resume_service(self, plugin_id: int, device_id: int, protocol: str, port: int) -> dict[str, Any]:
        """Resume a stopped port; its frozen plugin is kept."""
        body = {"device_id": device_id, "protocol": protocol, "port": port}
        data = self.request("POST", f"/api/plugin/{plugin_id}/services/resume", body).get("data")
        return data if isinstance(data, dict) else {}

    def plugin_matching(self, name: str) -> dict[str, Any]:
        """
        Return the inventory entry whose name equals `name` once a script extension is ignored
        (check_ncpa.py matches check_ncpa), so a plugin stored under its filename is found.
        """
        wanted = _without_extension(name)
        page = 1
        while True:
            data = self.get_data(f"/api/plugin?page={page}&per_page=100")
            if not isinstance(data, dict):
                raise HarnessError("Plugin inventory response is missing data.")
            for item in data.get("items", []):
                if _without_extension(str(item.get("name", ""))) == wanted:
                    return item
            if page >= int(data.get("pages", 1)):
                raise HarnessError(f"Required plugin {name} must have exactly one inventory entry.")
            page += 1

    def plugin_details(self, plugin_id: int) -> dict[str, Any]:
        """Return one plugin's details (service_driven, status, custom_checks)."""
        data = self.get_data(f"/api/plugin/{plugin_id}")
        if not isinstance(data, dict):
            raise HarnessError("Plugin details response is missing data.")
        return data

    def custom_checks(self, plugin_id: int, search: str = "") -> list[dict[str, Any]]:
        """Return every custom check of a plugin, across all pages, with live status."""
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            query = {"page": page, "per_page": 100}
            if search:
                query["search"] = search
            data = self.get_data(f"/api/plugin/{plugin_id}/custom-checks?{urlencode(query)}")
            if not isinstance(data, dict):
                raise HarnessError("Custom checks response is missing data.")
            items.extend(data.get("items", []))
            if page >= int(data.get("pages", 1)):
                return items
            page += 1

    def add_custom_check(
        self, plugin_id: int, name: str, variables: dict[str, Any], device_id: int | None = None,
    ) -> dict[str, Any]:
        """Add a custom check (a device check with device_id, a server check without)."""
        body: dict[str, Any] = {"name": name, "variables": variables}
        if device_id is not None:
            body["device_id"] = device_id
        data = self.request("POST", f"/api/plugin/{plugin_id}/custom-checks", body).get("data")
        return data if isinstance(data, dict) else {}

    def change_custom_check(
        self, plugin_id: int, check_id: int, name: str, variables: dict[str, Any],
        clear_secrets: list[str] | None = None,
    ) -> dict[str, Any]:
        """Rename a custom check and replace its arguments; a blank password keeps the stored one."""
        body: dict[str, Any] = {"name": name, "variables": variables}
        if clear_secrets:
            body["clear_secrets"] = clear_secrets
        data = self.request("PUT", f"/api/plugin/{plugin_id}/custom-checks/{check_id}", body).get("data")
        return data if isinstance(data, dict) else {}

    def pause_custom_check(self, plugin_id: int, check_id: int) -> dict[str, Any]:
        """Pause a custom check: its service leaves Nagios, the check stays listed."""
        data = self.request("POST", f"/api/plugin/{plugin_id}/custom-checks/{check_id}/pause").get("data")
        return data if isinstance(data, dict) else {}

    def resume_custom_check(self, plugin_id: int, check_id: int) -> dict[str, Any]:
        """Resume a paused custom check."""
        data = self.request("POST", f"/api/plugin/{plugin_id}/custom-checks/{check_id}/resume").get("data")
        return data if isinstance(data, dict) else {}

    def remove_custom_check(self, plugin_id: int, check_id: int) -> dict[str, Any]:
        """Remove a custom check and its service."""
        data = self.request("DELETE", f"/api/plugin/{plugin_id}/custom-checks/{check_id}").get("data")
        return data if isinstance(data, dict) else {}

    def wait_for_custom_check_status(
        self, plugin_id: int, check_id: int, timeout: int = 420, interval: int = 15,
    ) -> dict[str, Any]:
        """
        Poll until Nagios has run the check (its status is no longer "waiting") and return the
        item, or return the last item when the timeout passes so the caller can report it.
        """
        deadline = time.monotonic() + timeout
        item: dict[str, Any] = {}
        while True:
            matches = [entry for entry in self.custom_checks(plugin_id) if entry.get("id") == check_id]
            if not matches:
                raise HarnessError(f"Custom check {check_id} is no longer listed.")
            item = matches[0]
            if (item.get("status") or {}).get("kind") not in {"waiting", "stale"}:
                return item
            if time.monotonic() >= deadline:
                return item
            time.sleep(interval)

    def device_id(self, address: str, search_limit: int = 64) -> int:
        """
        Return the device id of the host at a lab address. No route lists
        devices with their IPs, so probe ids from 1 and match the address the
        ports route reports; a missing id (404) is skipped.
        """
        for candidate in range(1, search_limit + 1):
            status, body = self.call("GET", f"/api/system/hosts/{candidate}/ports")
            if status == 200 and ((body.get("data") or {}).get("device") or {}).get("ip_address") == address:
                return candidate
        raise HarnessError(f"No device record for {address}; run discovery first.")

    def device_ports(self, device_id: int) -> dict[str, Any]:
        """Return a device's ports grouped by state, with the reason for each."""
        data = self.get_data(f"/api/system/hosts/{device_id}/ports")
        if not isinstance(data, dict):
            raise HarnessError("Device ports response is missing data.")
        return data

    def port(self, device_id: int, protocol: str, number: int) -> dict[str, Any]:
        """Return one port row or raise when the device has no such port."""
        for item in self.device_ports(device_id).get("ports", []):
            if item.get("protocol") == protocol and item.get("number") == number:
                return item
        raise HarnessError(f"Device {device_id} has no {protocol}/{number} port.")

    def set_port(self, device_id: int, protocol: str, number: int, body: dict[str, Any]) -> dict[str, Any]:
        """Change a port (state, pin, acknowledge); the reply says whether Nagios was updated."""
        data = self.request("PUT", f"/api/system/hosts/{device_id}/ports/{protocol}/{number}", body).get("data")
        return data if isinstance(data, dict) else {}

    def review_items(self) -> list[dict[str, Any]]:
        """Return unresolved discovery review items (SERVICE_CHANGED, duplicates)."""
        data = self.get_data("/api/system/discover/review")
        if isinstance(data, dict):
            data = data.get("items", [])
        if not isinstance(data, list):
            raise HarnessError("Discovery review response is missing data.")
        return data

    def wait_for_plugin_service(
        self, plugin_id: int, service: str | None, service_prefix: str | None,
        timeout: int, interval: int,
    ) -> list[dict[str, Any]]:
        """Wait until a plugin lists the monitored service (not necessarily checked yet)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            matches = [
                item for item in self.plugin_services(plugin_id)
                if item.get("monitored") and (
                    (service is not None and item.get("service") == service)
                    or (service_prefix is not None and str(item.get("service", "")).startswith(service_prefix))
                )
            ]
            if matches:
                return matches
            time.sleep(interval)
        wanted = service or f"prefix {service_prefix}"
        raise HarnessError(f"Plugin {plugin_id} did not list service {wanted} within {timeout} seconds.")

    def require_status_feed(self, plugin_id: int, service: str | None, service_prefix: str | None) -> None:
        """
        Raise BlockedError when every matching service is still "waiting" (no check
        result has reached Pinpoint), which means the scheduler or the Nagios API
        account is not set up, not that the service is broken.
        """
        matches = [
            item for item in self.plugin_services(plugin_id)
            if item.get("service") == service or (
                service_prefix is not None and str(item.get("service", "")).startswith(service_prefix))
        ]
        if matches and all((item.get("status") or {}).get("kind") == "waiting" for item in matches):
            raise BlockedError(
                "Pinpoint shows every matching service as waiting for its first check. "
                "Run the app with PINPOINT_SCHEDULER=1 and a Nagios API account (see README)."
            )

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


def _without_extension(name: str) -> str:
    """The plugin name lowercased with a script extension removed (check_ncpa.py -> check_ncpa)."""
    lowered = name.strip().lower()
    for extension in (".py", ".pl", ".sh"):
        if lowered.endswith(extension):
            return lowered[: -len(extension)]
    return lowered


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
