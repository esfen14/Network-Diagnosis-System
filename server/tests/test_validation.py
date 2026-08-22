"""
tests/test_validation.py — Unit tests for helper/validation.py functions.

Pure unit tests — no Flask app context needed for these helpers.
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
    def test_validate_password_too_short(self):
        result = validate_password("Ab1!")
        assert result is not None
        msg, code = result
        assert code == 400
        assert "12" in msg["message"] or "characters" in msg["message"].lower()

    def test_validate_password_no_uppercase(self):
        result = validate_password("alllowercase1!")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_no_lowercase(self):
        result = validate_password("ALLUPPERCASE1!")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_no_digit(self):
        result = validate_password("NoDigitsHere!!")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_no_special(self):
        result = validate_password("NoSpecialChar1")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_password_valid(self):
        result = validate_password("ValidPass123!")
        assert result is None


# ─── validate_json_data ───────────────────────────────────────────────────────

class TestValidateJsonData:
    def test_validate_json_data_none(self):
        result = validate_json_data(None)
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_data_not_dict(self):
        result = validate_json_data(["a", "b"])
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_data_empty(self):
        result = validate_json_data({})
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_data_valid(self):
        result = validate_json_data({"key": "value"})
        assert result is None


# ─── validate_json_fields ─────────────────────────────────────────────────────

class TestValidateJsonFields:
    def test_validate_json_fields_missing(self):
        data = {"email": "user@example.com"}
        fields = {"email": str, "password": str}
        result = validate_json_fields(data, fields)
        assert result is not None
        msg, code = result
        assert code == 400
        assert "password" in msg["message"]

    def test_validate_json_fields_wrong_type(self):
        data = {"email": "user@example.com", "password": 12345}
        fields = {"email": str, "password": str}
        result = validate_json_fields(data, fields)
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_json_fields_valid(self):
        data = {"email": "user@example.com", "password": "hunter2"}
        fields = {"email": str, "password": str}
        result = validate_json_fields(data, fields)
        assert result is None


# ─── validate_user_email ──────────────────────────────────────────────────────

class TestValidateUserEmail:
    def test_validate_user_email_invalid(self):
        result = validate_user_email("not-an-email")
        assert result is not None
        _, code = result
        assert code == 400

    def test_validate_user_email_valid(self):
        result = validate_user_email("user@example.com")
        assert result is None
