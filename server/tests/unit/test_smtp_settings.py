"""
Tests for Settings -> Email: the validator and error classifier in
app/smtp_settings.py and the GET/PUT /api/system/smtp-settings and
POST /api/system/smtp-settings/test routes.

The root helper and SMTP are never contacted: subprocess.run and smtplib.SMTP are mocked.
"""
import json
import smtplib
import socket
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.smtp_settings import SmtpSettingsError, classify_smtp_error, validate_smtp_settings
from app.system_models import ConfigurationChanges, Permission, RolePermission, SmtpSettings

URL = "/api/system/smtp-settings"
TEST_URL = f"{URL}/test"
APP_PASSWORD = "abcd efgh ijkl mnop"
PAYLOAD = {"username": "ops@gmail.com", "password": APP_PASSWORD}


@pytest.fixture
def helper():
    """The root helper, replaced so nothing is written to /etc."""
    with patch("app.smtp_settings.subprocess.run",
               return_value=subprocess.CompletedProcess([], 0, "", "")) as mock:
        yield mock


@pytest.fixture(autouse=True)
def stable_key(app):
    app.config["SECRET_KEY"] = "test-secret"
    app.config["SECRET_KEY_IS_TEMPORARY"] = False


def grant(db_session, role, permission_name):
    permission = db_session.session.query(Permission).filter_by(Name=permission_name).one()
    db_session.session.add(RolePermission(RoleID=role.RoleID, PermissionID=permission.PermissionID))
    db_session.session.commit()


def save(client, version=0, **changes):
    return client.put(URL, json={**PAYLOAD, "version": version, **changes})


# ==========================================================
# VALIDATION
# ==========================================================

class TestValidate:

    def test_gmail_preset_values_are_filled_in(self):
        values = validate_smtp_settings(PAYLOAD, has_saved_password=False)

        assert (values["host"], values["port"], values["tls"]) == ("smtp.gmail.com", 587, "starttls")
        assert values["sender"] == "ops@gmail.com"

    def test_the_password_is_kept_exactly_as_typed(self):
        values = validate_smtp_settings({**PAYLOAD, "password": "  ab cd  "}, has_saved_password=False)

        assert values["password"] == "  ab cd  "

    def test_a_blank_password_keeps_the_saved_one(self):
        assert validate_smtp_settings({**PAYLOAD, "password": ""}, has_saved_password=True)["password"] is None

    def test_a_first_save_needs_a_password(self):
        with pytest.raises(SmtpSettingsError):
            validate_smtp_settings({"username": "ops@gmail.com"}, has_saved_password=False)

    @pytest.mark.parametrize("changes", [
        {"tls": "ssl"}, {"tls": "none"}, {"provider": "outlook"}, {"host": "smtp.example.com"}, {"port": 465},
        {"username": "ops"}, {"username": ""}, {"sender": "not an email"},
        {"password": "café"}, {"password": "line\nbreak"}, {"password": 12345}, {"password": "x" * 201},
    ])
    def test_rejects(self, changes):
        with pytest.raises(SmtpSettingsError):
            validate_smtp_settings({**PAYLOAD, **changes}, has_saved_password=False)


class TestClassify:

    def test_gmail_535_is_an_auth_failure_with_the_raw_text_kept(self):
        raw = b"5.7.8 Username and Password not accepted. For more information, go to https://support.google.com/mail/?p=BadCredentials"
        result = classify_smtp_error(smtplib.SMTPAuthenticationError(535, raw), "smtp.gmail.com", 587)

        assert result["code"] == "auth_failed"
        assert result["message"].startswith("Gmail rejected the login.")
        assert "535" in result["details"] and "BadCredentials" in result["details"]
        assert "app password" in result["explanation"] and "2-Step Verification" in result["explanation"]

    def test_a_refused_connection_is_a_blocked_port(self):
        result = classify_smtp_error(ConnectionRefusedError("refused"), "smtp.gmail.com", 587)

        assert result["code"] == "connect_failed"
        assert "port 587" in result["message"]
        assert "firewall" in result["explanation"]

    def test_a_timeout_is_a_blocked_port(self):
        assert classify_smtp_error(socket.timeout("timed out"), "smtp.gmail.com", 587)["code"] == "connect_failed"

    def test_an_unknown_host(self):
        assert classify_smtp_error(socket.gaierror(-2, "Name or service not known"), "smtp.gmail.com", 587)["code"] == "host_not_found"


# ==========================================================
# GET / PUT
# ==========================================================

class TestAccess:

    def test_requires_login(self, client, db_session):
        assert client.get(URL).status_code in (401, 302)

    def test_requires_the_email_permission(self, limited_client, db_session, regular_role):
        grant(db_session, regular_role, "settings.plugins")

        assert limited_client.get(URL).status_code == 403
        assert limited_client.put(URL, json=PAYLOAD).status_code == 403
        assert limited_client.post(TEST_URL).status_code == 403

    def test_the_email_permission_grants_access(self, limited_client, db_session, regular_role):
        grant(db_session, regular_role, "settings.email")

        assert limited_client.get(URL).status_code == 200


class TestGet:

    def test_unconfigured_returns_the_gmail_preset(self, logged_in_client, db_session):
        data = logged_in_client.get(URL).get_json()["data"]

        assert data["settings"]["configured"] is False
        assert data["settings"]["passwordSet"] is False
        assert data["presets"]["gmail"] == {"provider": "gmail", "host": "smtp.gmail.com", "port": 587, "tls": "starttls"}


class TestPut:

    def test_the_helper_gets_the_password_exactly_as_typed_on_stdin(self, logged_in_client, db_session, helper):
        assert save(logged_in_client).status_code == 200

        args, kwargs = helper.call_args
        assert args[0] == ["sudo", "-n", "/usr/local/sbin/pinpoint-apply-smtp"]
        assert json.loads(kwargs["input"]) == {
            "host": "smtp.gmail.com", "port": 587, "tls": "starttls",
            "username": "ops@gmail.com", "password": APP_PASSWORD, "sender": "ops@gmail.com",
        }

    def test_the_password_is_never_returned_or_stored_in_plain_text(self, logged_in_client, db_session, helper):
        body = save(logged_in_client)
        again = logged_in_client.get(URL)

        for response in (body, again):
            assert APP_PASSWORD not in response.get_data(as_text=True)
            assert "password" not in {key.lower() for key in response.get_json()["data"].get("settings", response.get_json()["data"])}
        assert again.get_json()["data"]["settings"]["passwordSet"] is True
        row = db_session.session.get(SmtpSettings, 1)
        assert APP_PASSWORD not in row.Password_Encrypted

    def test_a_blank_password_reuses_the_saved_one(self, logged_in_client, db_session, helper):
        save(logged_in_client)

        assert save(logged_in_client, version=1, password="", sender="other@gmail.com").status_code == 200
        assert json.loads(helper.call_args.kwargs["input"])["password"] == APP_PASSWORD

    def test_a_helper_refusal_is_shown_and_nothing_is_saved(self, logged_in_client, db_session):
        refusal = subprocess.CompletedProcess([], 1, "", "username must be printable ASCII")
        with patch("app.smtp_settings.subprocess.run", return_value=refusal):
            response = save(logged_in_client)

        assert response.status_code == 400
        assert response.get_json()["message"] == "username must be printable ASCII"
        assert db_session.session.get(SmtpSettings, 1) is None

    def test_a_missing_helper_is_a_server_error(self, logged_in_client, db_session):
        with patch("app.smtp_settings.subprocess.run", side_effect=FileNotFoundError):
            response = save(logged_in_client)

        assert response.status_code == 500
        assert "not installed" in response.get_json()["message"]

    def test_a_stale_version_is_a_conflict(self, logged_in_client, db_session, helper):
        save(logged_in_client)

        assert save(logged_in_client, version=0).status_code == 409

    @pytest.mark.parametrize("changes", [{"tls": "ssl"}, {"tls": "none"}, {"provider": "outlook"}])
    def test_other_modes_and_providers_are_refused(self, logged_in_client, db_session, helper, changes):
        assert save(logged_in_client, **changes).status_code == 400
        helper.assert_not_called()

    def test_the_change_is_logged_without_the_password(self, logged_in_client, db_session, helper):
        save(logged_in_client)

        rows = db_session.session.query(ConfigurationChanges).filter_by(Conf_Type="smtp_settings").all()
        assert {row.Parameter_Name for row in rows} >= {"username", "password"}
        assert all(APP_PASSWORD not in f"{row.Old_Value}{row.New_Value}" for row in rows)


# ==========================================================
# POST /test
# ==========================================================

class TestSendTest:

    def smtp(self, **attrs):
        mock = MagicMock()
        for name, value in attrs.items():
            getattr(mock.return_value.__enter__.return_value, name).side_effect = value
        return patch("app.smtp_settings.smtplib.SMTP", mock), mock

    def test_needs_saved_settings(self, logged_in_client, db_session):
        assert logged_in_client.post(TEST_URL).status_code == 400

    def test_a_good_send_uses_starttls_and_the_saved_password(self, logged_in_client, db_session, helper):
        save(logged_in_client)
        patcher, mock = self.smtp()
        with patcher:
            data = logged_in_client.post(TEST_URL).get_json()["data"]

        assert data["ok"] is True
        conn = mock.return_value.__enter__.return_value
        conn.starttls.assert_called_once()
        conn.login.assert_called_once_with("ops@gmail.com", APP_PASSWORD)
        mock.assert_called_once_with("smtp.gmail.com", 587, timeout=15)

    def test_gmails_535_gives_the_friendly_message_and_the_raw_text(self, logged_in_client, db_session, helper):
        save(logged_in_client)
        raw = b"5.7.8 Username and Password not accepted. For more information, go to https://support.google.com/mail/?p=BadCredentials"
        patcher, _ = self.smtp(login=smtplib.SMTPAuthenticationError(535, raw))
        with patcher:
            data = logged_in_client.post(TEST_URL).get_json()["data"]

        assert data["ok"] is False and data["code"] == "auth_failed"
        assert data["message"] == ("Gmail rejected the login. Make sure you entered an app password, "
                                   "not your normal password, and that 2-Step Verification is on.")
        assert "BadCredentials" in data["details"]
        assert "535" in data["explanation"]
        assert APP_PASSWORD not in json.dumps(data)

    def test_a_blocked_port_has_its_own_message(self, logged_in_client, db_session, helper):
        save(logged_in_client)
        patcher, _ = self.smtp(ehlo=ConnectionRefusedError("refused"))
        with patcher:
            data = logged_in_client.post(TEST_URL).get_json()["data"]

        assert data["code"] == "connect_failed"
        assert "Gmail rejected" not in data["message"]
