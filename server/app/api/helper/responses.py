from flask import jsonify


def success(data=None, message=None, status=200):
    """
    Return a standardized success response.

    Usage:
        return success({"items": [...]})
        return success(message="User created.", status=201)
        return success({"id": 1, "name": "Admin"})
    """
    body = {"success": True}

    if message is not None:
        body["message"] = message

    if data is not None:
        body["data"] = data

    return jsonify(body), status


def error(message, status=400, data=None):
    """
    Return a standardized error response. ``data`` is optional detail the
    client needs to act on the error (e.g. which devices were rejected).

    Usage:
        return error("Invalid email.", 400)
        return error("Not found.", 404)
        return error("Unauthorized.", 401)
        return error("No devices could be deployed.", 400, {"rejected": [...]})
    """
    body = {
        "success": False,
        "message": message
    }

    if data is not None:
        body["data"] = data

    return jsonify(body), status
