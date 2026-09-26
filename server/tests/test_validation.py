"""
tests/test_validation.py — Unit tests for helper/validation.py functions.

The validation helpers return Flask response tuples (via jsonify), so each
test runs inside an application context. validate_password also reads the
Strong Password Policy flag from SystemSettings, so those tests use db_session
(tables exist, no settings row -> strong policy applies by default).
"""
import pytest

from app.api.helper.validation import (
    validate_password,
    validate_json_data,
    validate_json_fields,
    validate_user_email,
)


# ─── validate_password ────────────────────────────────────────────────────────

class TestValidatePassword:
    def test_validate_password_too_short(self, db_session):
        result = validate_password("Ab1!")
        assert result is not None
        msg, code = result
        assert code == 400
        assert "12" in msg.get_json()["message"] or "characters" in msg.get_json()["message"].lower()

    def test_validate_password_no_uppercase(self, db_session):
        result = validate_password("alllowercase1!")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_no_lowercase(self, db_session):
        result = validate_password("ALLUPPERCASE1!")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_no_digit(self, db_session):
        result = validate_password("NoDigitsHere!!")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_no_special(self, db_session):
        result = validate_password("NoSpecialChar1")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_valid(self, db_session):
        result = validate_password("ValidPass123!")
        assert result is None


# ─── validate_json_data ───────────────────────────────────────────────────────

class TestValidateJsonData:
    def test_validate_json_data_none(self, app):
        with app.app_context():
            result = validate_json_data(None)
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_data_not_dict(self, app):
        with app.app_context():
            result = validate_json_data(["a", "b"])
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_data_empty(self, app):
        with app.app_context():
            result = validate_json_data({})
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_data_valid(self, app):
        with app.app_context():
            result = validate_json_data({"key": "value"})
        assert result is None


# ─── validate_json_fields ─────────────────────────────────────────────────────

class TestValidateJsonFields:
    def test_validate_json_fields_missing(self, app):
        data = {"email": "user@example.com"}
        fields = {"email": str, "password": str}
        with app.app_context():
            result = validate_json_fields(data, fields)
        assert result is not None
        msg, code = result
        assert code == 400
        assert "password" in msg.get_json()["message"]

    def test_validate_json_fields_wrong_type(self, app):
        data = {"email": "user@example.com", "password": 12345}
        fields = {"email": str, "password": str}
        with app.app_context():
            result = validate_json_fields(data, fields)
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_fields_valid(self, app):
        data = {"email": "user@example.com", "password": "hunter2"}
        fields = {"email": str, "password": str}
        with app.app_context():
            result = validate_json_fields(data, fields)
        assert result is None


# ─── validate_user_email ──────────────────────────────────────────────────────

class TestValidateUserEmail:
    def test_validate_user_email_invalid(self, app):
        with app.app_context():
            result = validate_user_email("not-an-email")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_user_email_valid(self, app):
        with app.app_context():
            result = validate_user_email("user@example.com")
        assert result is None
