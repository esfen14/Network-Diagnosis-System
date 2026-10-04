# Isolated backend tests

This directory contains the isolated regression suite. It includes pure unit
tests and mocked Flask API/database integration tests; the folder name does not
classify every test as a pure unit test. Shared fixtures remain in
`server/conftest.py`, and builders live in `../support/`.

From `server/`, run `.venv/bin/python -m pytest` or target `tests/unit/`.
No live Nagios, discovery, SSH deployment, or guest-control tests belong here.
See the [test guide](../README.md).
