"""
Identity probes for Network Discovery.

Small, read-only network probes that collect evidence for the device
reconciler in device_identity.py: the NCPA TLS certificate fingerprint and
the SSH host key fingerprint. Both identify a machine without sending any
secret: the TLS probe only completes a handshake and reads the certificate,
and never sends an NCPA token; the SSH probe only reads the server's host key.
A probe that fails returns None and is simply skipped, so an unreachable
service never blocks a scan.
"""

import base64
import hashlib
import socket
import ssl

import paramiko
from flask import current_app

from app.system_models import IdentifierKind

PROBE_TIMEOUT = 3


def tls_certificate_fingerprint(ip_address, port, timeout=PROBE_TIMEOUT):
    """
    Return the lower-case hex SHA-256 fingerprint of the certificate the
    service on ip_address:port presents, or None if it cannot be read.
    Certificate validity is deliberately not checked (NCPA uses a self-signed
    certificate); the fingerprint is the identity. Sends no application data.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((ip_address, int(port)), timeout=timeout) as raw:
            with context.wrap_socket(raw) as tls:
                der = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError, ValueError):
        return None

    if not der:
        return None
    return hashlib.sha256(der).hexdigest()


def ssh_host_key_fingerprint(ip_address, port=22, timeout=PROBE_TIMEOUT):
    """
    Return the SSH host key fingerprint of ip_address in the same format the
    NCPA deployment stores in SSHCredentials.Key_Fingerprint (unpadded base64
    SHA-256), or None if the host does not answer as an SSH server.
    """
    transport = None
    try:
        transport = paramiko.Transport((ip_address, int(port)))
        transport.start_client(timeout=timeout)
        key = transport.get_remote_server_key()
        digest = hashlib.sha256(key.asbytes()).digest()
        return base64.b64encode(digest).decode("utf-8").rstrip("=")
    except (paramiko.SSHException, OSError, EOFError):
        return None
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass


def collect_identifiers(ip_address, tcp_ports):
    """
    Probe one host for identity evidence based on its open TCP ports: the
    NCPA certificate if the NCPA port is open, the SSH host key if port 22 is.
    Returns a list of (IdentifierKind, value) pairs, possibly empty.
    """
    ports = {str(port) for port in tcp_ports or {}}
    identifiers = []

    ncpa_port = str(current_app.config["NCPA_PORT"])
    if ncpa_port in ports:
        fingerprint = tls_certificate_fingerprint(ip_address, ncpa_port)
        if fingerprint:
            identifiers.append((IdentifierKind.NCPA_CERT, fingerprint))

    ssh_port = str(current_app.config.get("SSH_PORT", 22))
    if ssh_port in ports:
        fingerprint = ssh_host_key_fingerprint(ip_address, ssh_port)
        if fingerprint:
            identifiers.append((IdentifierKind.SSH_HOST_KEY, fingerprint))

    return identifiers
