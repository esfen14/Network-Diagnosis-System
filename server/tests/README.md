# Tests — Network Diagnosis System (Server)

This folder contains all pytest tests for the Flask API server.

---

## Quick Start

All commands are run from the **`server/`** directory (the folder that contains `conftest.py`).

### 1. Install test dependencies (first time only)

```bash
.venv/bin/pip install -r requirements-test.txt
```

### 2. Run all tests

```bash
.venv/bin/python -m pytest tests/ -v
```

### 3. Run a single test file

```bash
.venv/bin/python -m pytest tests/test_notifications.py -v
```

### 4. Run a single test class or test

```bash
# A whole class
.venv/bin/python -m pytest tests/test_notifications.py::TestGetNotifications -v

# A single test
.venv/bin/python -m pytest tests/test_notifications.py::TestGetNotifications::test_requires_login -v
```

### 5. Run tests matching a keyword

```bash
.venv/bin/python -m pytest tests/ -k "login" -v
```

---

## Test Files

| File | What it covers |
|---|---|
| `test_auth.py` | `POST /api/user/login`, `POST /api/user/logout` |
| `test_management.py` | Role and user account management endpoints |
| `test_inventory.py` | Host inventory endpoints |
| `test_validation.py` | Input validation helpers |
| `test_ncpa.py` | NCPA deployment endpoints |
| `test_network_discovery.py` | Network discovery endpoints |
| `test_notifications.py` | `GET/POST /api/system/notifications*` (cursor-based read tracking) |
| `test_report_notifications_alerts.py` | `GET /api/system/report/alerts` and `GET /api/system/report/notifications` |

---

## How the Test Setup Works

### `conftest.py` (in `server/`)

This file runs automatically before any test. It does three things:

1. **Swaps the databases for in-memory SQLite** — no real database files are touched during tests.
2. **Defines reusable fixtures** — building blocks every test file can use (see below).
3. **Seeds permissions** — the `PERMISSION_NAMES` list at the top of `conftest.py` controls which permissions exist in every test database. If you add a new permission to your app, add it here too.

### Fixtures

Fixtures are injected into tests as function arguments. The most useful ones:

| Fixture | What it gives you |
|---|---|
| `client` | A Flask test client — not logged in |
| `db_session` | A clean in-memory database, wiped after each test |
| `seeded_permissions` | All permissions from `PERMISSION_NAMES` inserted into the DB |
| `admin_user` | An active user with the Admin role (all permissions) |
| `regular_user` | An active user with only `system.inventory` permission |
| `logged_in_client` | A `client` already authenticated as `admin_user` |
| `limited_client` | A `client` already authenticated as `regular_user` |

Fixtures are **function-scoped** by default — each test gets a fresh state.

---

## How to Add a New Test File

### Step 1 — Create the file

Name it `test_<feature>.py` inside this folder. The `test_` prefix is required for pytest to pick it up.

### Step 2 — Add the permission (if needed)

If the route you're testing uses `@require_permission("some.permission")`, open `conftest.py` and add `"some.permission"` to the `PERMISSION_NAMES` list so the `admin_user` fixture has access to it.

```python
# conftest.py
PERMISSION_NAMES = [
    ...
    "some.permission",   # <-- add here
]
```

### Step 3 — Write the test

Use pytest classes to group related tests. Always inject `db_session` when the route touches the database.

```python
import pytest

class TestMyRoute:

    def test_requires_login(self, client, db_session):
        resp = client.get("/api/system/my-route")
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session, seeded_permissions):
        resp = limited_client.get("/api/system/my-route")
        assert resp.status_code == 403

    def test_happy_path(self, logged_in_client, db_session, seeded_permissions):
        resp = logged_in_client.get("/api/system/my-route")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
```

### Step 4 — Mock external services (Nagios, SSH, etc.)

Routes that call Nagios or run SSH commands must be mocked — there is no live server in tests. Use `unittest.mock.patch` and always patch at the location where the function is **used** (inside the route module), not where it is defined.

```python
from unittest.mock import patch

# ✅ Correct — patch where the route looks it up
PATCH_TARGET = "app.api.system.my_module.request_notifications_range"

# ❌ Wrong — patching the original source has no effect on the route
# PATCH_TARGET = "app.nagios.notifications.request_notifications_range"

def test_nagios_returns_data(self, logged_in_client, db_session, seeded_permissions):
    fake_data = [{"timestamp": 1700000000, "host_name": "host1"}]

    with patch(PATCH_TARGET, return_value=fake_data):
        resp = logged_in_client.get("/api/system/my-route")

    assert resp.status_code == 200

def test_nagios_unreachable(self, logged_in_client, db_session, seeded_permissions):
    with patch(PATCH_TARGET, return_value=None):
        resp = logged_in_client.get("/api/system/my-route")

    assert resp.status_code == 502
```

---

## Checklist for Every New Route Test

- [ ] Unauthenticated request → `401` or `302`
- [ ] Authenticated but wrong permission → `403`
- [ ] Happy path → `200` with the expected response shape
- [ ] External services mocked (Nagios, SSH, etc.)
- [ ] Nagios/external returning `None` → `502`
- [ ] Invalid inputs → `400`
- [ ] Empty data → `200` with sensible defaults (empty list, zero count, etc.)
