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
    Probe one host for identity evidence based on its open TCP ports
    ({port: {"service_name": ...}}): the NCPA certificate if the NCPA port is
    open, and the SSH host key on the standard SSH port and on every port nmap
    identified as ssh, so SSH on a non-standard port is still evidence. Each
    distinct value is reported once. Returns a list of (IdentifierKind, value)
    pairs, possibly empty.
    """
    tcp_ports = tcp_ports or {}
    ports = {str(port) for port in tcp_ports}
    identifiers = []

    ncpa_port = str(current_app.config["NCPA_PORT"])
    if ncpa_port in ports:
        fingerprint = tls_certificate_fingerprint(ip_address, ncpa_port)
        if fingerprint:
            identifiers.append((IdentifierKind.NCPA_CERT, fingerprint))

    for ssh_port in ssh_ports_to_probe(tcp_ports):
        fingerprint = ssh_host_key_fingerprint(ip_address, int(ssh_port))
        if fingerprint and (IdentifierKind.SSH_HOST_KEY, fingerprint) not in identifiers:
            identifiers.append((IdentifierKind.SSH_HOST_KEY, fingerprint))

    return identifiers


def ssh_ports_to_probe(tcp_ports):
    """
    The open ports worth an SSH host-key probe, as strings: the standard
    SSH_PORT if it is open, then every other port nmap named ssh, in port
    order.
    """
    standard_port = str(current_app.config["SSH_PORT"])
    selected = []
    if standard_port in {str(port) for port in tcp_ports}:
        selected.append(standard_port)

    for port, service_data in sorted(tcp_ports.items(), key=lambda item: int(item[0])):
        service_name = str((service_data or {}).get("service_name") or "").strip().lower()
        if service_name == "ssh" and str(port) not in selected:
            selected.append(str(port))
    return selected
