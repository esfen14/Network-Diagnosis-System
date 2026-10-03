#!/usr/bin/env bash
# Prepare privileged host prerequisites for the live Network Discovery test.
# Preview-only unless --apply is supplied. This script never installs plugins,
# runs discovery, reloads Nagios, or changes guest services.
set -euo pipefail

ACTION="preview"
OPERATOR="paeng"
APP_ACCOUNT="pinpoint"
LAB_NETWORK="pinpoint-test"
TARGET01="pinpoint-test-target01"
TARGET02="pinpoint-test-target02"
VM_STATE="/var/lib/libvirt/images/pinpoint-lab"
NCPA_KEY="/opt/pinpoint/.ssh/pinpoint_ncpa_deploy"
SUDOERS_FILE="/etc/sudoers.d/pinpoint-live-tests"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HARNESS_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
LAB_CONFIG="${HARNESS_DIR}/config/lab.json"
LAB_EXAMPLE="${HARNESS_DIR}/config/lab.example.json"
VM_CONFIG="${HARNESS_DIR}/vm_scripts/vm-lab.json"

SESSION_STATE="/opt/pinpoint/Network-Diagnosis-System/.cache/pinpoint-lab-20261003"
if [[ -d "${SESSION_STATE}" ]]; then
  VM_STATE="${SESSION_STATE}"
fi
if [[ -f "${VM_STATE}/vm-lab.json" ]]; then
  VM_CONFIG="${VM_STATE}/vm-lab.json"
fi

usage() {
  cat <<'EOF'
Usage: prepare_test_host.sh [--apply | --check] [options]

Preview is the default and makes no changes. Run --apply as root to:
  - grant the scoped Nagios and NCPA-key ACLs required by the test operator;
  - create or verify the exact-command temporary Nagios reload sudoers rule;
  - create the protected environment file and result directory if absent;
  - create lab.json from the reviewed example if absent;
  - start the existing isolated libvirt network and two disposable domains;
  - validate Nagios, libvirt isolation, configuration, and existing VM state.

This script does not install Nagios plugins, run discovery, reload Nagios,
create VMs, modify guest services, or read credential/private-key contents.

Options:
  --apply                 Apply preparation and then run checks (requires root).
  --check                 Re-run validation without applying host setup;
                          VM verification may refresh inventory evidence.
  --operator USER         Test operator (default: paeng).
  --app-account USER      Pinpoint service account (default: pinpoint).
  --network NAME          Existing libvirt lab network (default: pinpoint-test).
  --target01 NAME         Existing first domain.
  --target02 NAME         Existing second domain.
  --lab-config PATH       Runtime harness manifest.
  --vm-config PATH        Existing VM-kit manifest.
  --state-dir PATH        Existing VM-kit state directory.
  --ncpa-key PATH         Existing NCPA deployment private key.
  --sudoers-file PATH     Temporary operator sudoers file.
  -h, --help              Show this help.
EOF
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

note() {
  echo "==> $*"
}

require_safe_name() {
  local label="$1"
  local value="$2"
  [[ "${value}" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "${label} contains unsafe characters: ${value}"
}

require_absolute_path() {
  local label="$1"
  local value="$2"
  [[ "${value}" == /* ]] || fail "${label} must be an absolute path: ${value}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      [[ "${ACTION}" == "preview" ]] || fail "Choose only one action."
      ACTION="apply"
      shift
      ;;
    --check)
      [[ "${ACTION}" == "preview" ]] || fail "Choose only one action."
      ACTION="check"
      shift
      ;;
    --operator|--app-account|--network|--target01|--target02|--lab-config|--vm-config|--state-dir|--ncpa-key|--sudoers-file)
      [[ $# -ge 2 ]] || fail "$1 requires a value."
      case "$1" in
        --operator) OPERATOR="$2" ;;
        --app-account) APP_ACCOUNT="$2" ;;
        --network) LAB_NETWORK="$2" ;;
        --target01) TARGET01="$2" ;;
        --target02) TARGET02="$2" ;;
        --lab-config) LAB_CONFIG="$2" ;;
        --vm-config) VM_CONFIG="$2" ;;
        --state-dir) VM_STATE="$2" ;;
        --ncpa-key) NCPA_KEY="$2" ;;
        --sudoers-file) SUDOERS_FILE="$2" ;;
      esac
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

require_safe_name "operator" "${OPERATOR}"
require_safe_name "application account" "${APP_ACCOUNT}"
require_safe_name "network" "${LAB_NETWORK}"
require_safe_name "target01" "${TARGET01}"
require_safe_name "target02" "${TARGET02}"
require_absolute_path "lab config" "${LAB_CONFIG}"
require_absolute_path "VM config" "${VM_CONFIG}"
require_absolute_path "VM state" "${VM_STATE}"
require_absolute_path "NCPA key" "${NCPA_KEY}"
require_absolute_path "sudoers file" "${SUDOERS_FILE}"

OPERATOR_HOME="$(getent passwd "${OPERATOR}" | cut -d: -f6 || true)"
if [[ -z "${OPERATOR_HOME}" ]]; then
  [[ "${ACTION}" == "preview" ]] || fail "Operator account does not exist: ${OPERATOR}"
  OPERATOR_HOME="/home/${OPERATOR}"
fi
OPERATOR_GROUP="$(id -gn "${OPERATOR}" 2>/dev/null || printf '%s' "${OPERATOR}")"
ENV_DIR="${OPERATOR_HOME}/.config/pinpoint-tests"
ENV_FILE="${ENV_DIR}/lab.env"
OUTPUT_ROOT="${OPERATOR_HOME}/pinpoint-test-results"

show_plan() {
  cat <<EOF
Preview only; no files, permissions, services, networks, or domains were changed.

Operator:           ${OPERATOR}
Application account: ${APP_ACCOUNT}
Lab network:        ${LAB_NETWORK}
Domains:            ${TARGET01}, ${TARGET02}
Harness config:     ${LAB_CONFIG}
VM config:          ${VM_CONFIG}
VM state:           ${VM_STATE}
Environment file:  ${ENV_FILE}
Result directory:  ${OUTPUT_ROOT}
Temporary sudoers: ${SUDOERS_FILE}

Run this reviewed command to apply the preparation:
  sudo bash ${SCRIPT_DIR}/prepare_test_host.sh --apply

Plugin installation, discovery, Nagios reload, VM creation, guest mutation,
credential loading, and private-key content access are deliberately excluded.
EOF
}

if [[ "${ACTION}" == "preview" ]]; then
  show_plan
  exit 0
fi

[[ "${EUID}" -eq 0 ]] || fail "${ACTION} must run as root."

for command in getent id setfacl getfacl virsh ip python3 runuser sudo systemctl visudo; do
  command -v "${command}" >/dev/null 2>&1 || fail "Required command is missing: ${command}"
done

getent passwd "${OPERATOR}" >/dev/null || fail "Operator account does not exist: ${OPERATOR}"
getent passwd "${APP_ACCOUNT}" >/dev/null || fail "Application account does not exist: ${APP_ACCOUNT}"

NAGIOS_BIN="/usr/local/nagios/bin/nagios"
NAGIOS_CFG="/usr/local/nagios/etc/nagios.cfg"
NAGIOS_RESOURCE="/usr/local/nagios/etc/resource.cfg"
NAGIOS_SPOOL="/usr/local/nagios/var/spool/checkresults"
SYSTEMCTL_BIN="$(readlink -f "$(command -v systemctl)")"

for path in "${NAGIOS_BIN}" "${NAGIOS_CFG}" "${NAGIOS_RESOURCE}" "${NCPA_KEY}"; do
  [[ -f "${path}" ]] || fail "Required file does not exist: ${path}"
done
[[ -d "${NAGIOS_SPOOL}" ]] || fail "Required directory does not exist: ${NAGIOS_SPOOL}"
[[ -d "$(dirname -- "${NCPA_KEY}")" ]] || fail "NCPA SSH directory does not exist."
[[ -f "${LAB_EXAMPLE}" ]] || fail "Reviewed lab example is missing: ${LAB_EXAMPLE}"

install_operator_sudoers() {
  local expected
  local temporary
  expected="${OPERATOR} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} reload nagios"

  if [[ -e "${SUDOERS_FILE}" ]]; then
    visudo -cf "${SUDOERS_FILE}" >/dev/null
    note "Preserved existing valid sudoers file: ${SUDOERS_FILE}"
    return
  fi

  temporary="$(mktemp /tmp/pinpoint-live-sudoers.XXXXXX)"
  trap 'rm -f "${temporary:-}"' RETURN
  printf '%s\n' "${expected}" > "${temporary}"
  chmod 0440 "${temporary}"
  visudo -cf "${temporary}" >/dev/null
  install -o root -g root -m 0440 "${temporary}" "${SUDOERS_FILE}"
  visudo -c >/dev/null
  rm -f "${temporary}"
  trap - RETURN
  note "Installed exact-command operator sudoers rule: ${SUDOERS_FILE}"
}

start_network() {
  if ! virsh -c qemu:///system net-info "${LAB_NETWORK}" >/dev/null 2>&1; then
    fail "Existing libvirt network was not found: ${LAB_NETWORK}"
  fi
  if [[ "$(virsh -c qemu:///system net-info "${LAB_NETWORK}" | awk '/^Active:/ {print $2}')" != "yes" ]]; then
    virsh -c qemu:///system net-start "${LAB_NETWORK}" >/dev/null
    note "Started libvirt network ${LAB_NETWORK}."
  else
    note "Libvirt network ${LAB_NETWORK} is already active."
  fi
}

start_domain() {
  local domain="$1"
  local state
  virsh -c qemu:///system dominfo "${domain}" >/dev/null 2>&1 || fail "Existing domain was not found: ${domain}"
  state="$(virsh -c qemu:///system domstate "${domain}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${state}" != "running" ]]; then
    virsh -c qemu:///system start "${domain}" >/dev/null
    note "Started domain ${domain}."
  else
    note "Domain ${domain} is already running."
  fi
}

validate_manifest() {
  python3 - "${LAB_CONFIG}" "${OUTPUT_ROOT}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_output = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
expected = {
    "lab_network": "10.0.2.0/28",
    "pinpoint_address": "10.0.2.1",
    "target01_address": "10.0.2.2",
    "target02_address": "10.0.2.3",
    "database": "/opt/pinpoint/Network-Diagnosis-System/server/system.db",
    "output_root": expected_output,
}
actual = {
    "lab_network": data.get("lab_network"),
    "pinpoint_address": data.get("pinpoint", {}).get("address"),
    "target01_address": data.get("targets", {}).get("target01", {}).get("address"),
    "target02_address": data.get("targets", {}).get("target02", {}).get("address"),
    "database": data.get("databases", {}).get("system"),
    "output_root": data.get("output_root"),
}
errors = [f"{key}: expected {expected[key]!r}, found {actual[key]!r}" for key in expected if actual[key] != expected[key]]
pinpoint = data.get("pinpoint", {})
if pinpoint.get("email_env") != "PINPOINT_TEST_EMAIL":
    errors.append("pinpoint.email_env must be PINPOINT_TEST_EMAIL")
if pinpoint.get("password_env") != "PINPOINT_TEST_PASSWORD":
    errors.append("pinpoint.password_env must be PINPOINT_TEST_PASSWORD")
for name in ("target01", "target02"):
    if data.get("targets", {}).get(name, {}).get("ssh_key_env") != "PINPOINT_TEST_SSH_KEY":
        errors.append(f"targets.{name}.ssh_key_env must be PINPOINT_TEST_SSH_KEY")
if not str(pinpoint.get("base_url", "")).startswith(("http://", "https://")):
    errors.append("pinpoint.base_url must be reviewed and use http:// or https://")
if errors:
    raise SystemExit("Unsafe or incomplete lab.json:\n- " + "\n- ".join(errors))
print(f"Validated lab manifest: {path}")
print(f"Pinpoint API URL for operator review: {pinpoint['base_url']}")
PY
}

prepare_manifest() {
  python3 - "${LAB_CONFIG}" "${LAB_EXAMPLE}" "${OUTPUT_ROOT}" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
example = Path(sys.argv[2])
output_root = sys.argv[3]
source = path if path.exists() else example
data = json.loads(source.read_text(encoding="utf-8"))

# Normalize only the approved host-specific safety values. Preserve the API URL,
# port lists, hostnames, and other reviewed test behavior from an existing file.
data["lab_network"] = "10.0.2.0/28"
data.setdefault("pinpoint", {})["address"] = "10.0.2.1"
data["pinpoint"]["email_env"] = "PINPOINT_TEST_EMAIL"
data["pinpoint"]["password_env"] = "PINPOINT_TEST_PASSWORD"
data.setdefault("targets", {}).setdefault("target01", {})["address"] = "10.0.2.2"
data["targets"].setdefault("target02", {})["address"] = "10.0.2.3"
data["targets"]["target01"]["ssh_key_env"] = "PINPOINT_TEST_SSH_KEY"
data["targets"]["target02"]["ssh_key_env"] = "PINPOINT_TEST_SSH_KEY"
data.setdefault("databases", {})["system"] = "/opt/pinpoint/Network-Diagnosis-System/server/system.db"
data["output_root"] = output_root

path.parent.mkdir(parents=True, exist_ok=True)
descriptor, temporary_name = tempfile.mkstemp(prefix=".lab.", suffix=".json", dir=path.parent)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary_name, 0o600)
    os.replace(temporary_name, path)
finally:
    if os.path.exists(temporary_name):
        os.unlink(temporary_name)
PY
}

validate_domain_interface() {
  local domain="$1"
  local -a sources=()
  mapfile -t sources < <(
    virsh -c qemu:///system domiflist "${domain}" |
      awk 'NR > 2 && NF >= 5 {print $3}'
  )
  [[ "${#sources[@]}" -eq 1 ]] || fail "${domain} must have exactly one interface; found ${#sources[@]}."
  [[ "${sources[0]}" == "${LAB_NETWORK}" ]] || fail "${domain} is attached to ${sources[0]}, not only ${LAB_NETWORK}."
}

if [[ "${ACTION}" == "apply" ]]; then
  note "Applying scoped ACLs."
  setfacl -m "u:${OPERATOR}:rx" "${NAGIOS_BIN}"
  setfacl -m "u:${OPERATOR}:rwx" "${NAGIOS_SPOOL}"
  setfacl -m "u:${OPERATOR}:r" "${NAGIOS_RESOURCE}"
  setfacl -m "u:${OPERATOR}:x" "$(dirname -- "${NCPA_KEY}")"
  setfacl -m "u:${OPERATOR}:r" "${NCPA_KEY}"

  install_operator_sudoers

  install -d -o "${OPERATOR}" -g "${OPERATOR_GROUP}" -m 0700 "${ENV_DIR}"
  if [[ ! -e "${ENV_FILE}" ]]; then
    install -o "${OPERATOR}" -g "${OPERATOR_GROUP}" -m 0600 /dev/null "${ENV_FILE}"
    note "Created empty protected environment file; the tester must populate it: ${ENV_FILE}"
  else
    chown "${OPERATOR}:${OPERATOR_GROUP}" "${ENV_FILE}"
    chmod 0600 "${ENV_FILE}"
  fi
  install -d -o "${OPERATOR}" -g "${OPERATOR_GROUP}" -m 0700 "${OUTPUT_ROOT}"

  prepare_manifest
  chown "${OPERATOR}:${OPERATOR_GROUP}" "${LAB_CONFIG}"
  chmod 0600 "${LAB_CONFIG}"
  note "Normalized the runtime manifest to the approved isolated addresses and host paths."

  start_network
  start_domain "${TARGET01}"
  start_domain "${TARGET02}"
fi

note "Validating scoped access without reading secret contents."
getfacl -p "${NAGIOS_BIN}" "${NAGIOS_SPOOL}" "${NAGIOS_RESOURCE}" \
  "$(dirname -- "${NCPA_KEY}")" "${NCPA_KEY}" >/dev/null
runuser -u "${OPERATOR}" -- test -r "${NAGIOS_RESOURCE}"
runuser -u "${OPERATOR}" -- test -r "${NCPA_KEY}"
runuser -u "${OPERATOR}" -- test -x "$(dirname -- "${NCPA_KEY}")"

visudo -cf "${SUDOERS_FILE}" >/dev/null
sudo -n -l -U "${OPERATOR}" "${SYSTEMCTL_BIN}" reload nagios >/dev/null
sudo -n -l -U "${APP_ACCOUNT}" "${SYSTEMCTL_BIN}" reload nagios >/dev/null
systemctl is-active --quiet nagios || fail "Nagios is not active."
runuser -u "${OPERATOR}" -- "${NAGIOS_BIN}" -v "${NAGIOS_CFG}"

[[ -f "${LAB_CONFIG}" ]] || fail "Runtime lab manifest is missing: ${LAB_CONFIG}"
validate_manifest

if [[ "$(virsh -c qemu:///system net-info "${LAB_NETWORK}" | awk '/^Active:/ {print $2}')" != "yes" ]]; then
  fail "Libvirt network is not active: ${LAB_NETWORK}"
fi
for domain in "${TARGET01}" "${TARGET02}"; do
  [[ "$(virsh -c qemu:///system domstate "${domain}" | tr '[:upper:]' '[:lower:]')" == "running" ]] || \
    fail "Libvirt domain is not running: ${domain}"
done

if virsh -c qemu:///system net-dumpxml "${LAB_NETWORK}" | grep -Eq '<forward([[:space:]>])'; then
  fail "${LAB_NETWORK} has forwarding enabled; it is not isolated."
fi
validate_domain_interface "${TARGET01}"
validate_domain_interface "${TARGET02}"

if [[ -f "${VM_CONFIG}" && -f "${VM_STATE}/state.json" ]]; then
  note "Running the existing VM kit's route, listener, SSH, ownership, and baseline verification."
  python3 "${HARNESS_DIR}/vm_scripts/provision_lab.py" verify \
    --config "${VM_CONFIG}" --state-dir "${VM_STATE}"
else
  fail "VM verification inputs are missing: ${VM_CONFIG} and/or ${VM_STATE}/state.json"
fi

cat <<EOF

Host preparation passed. No plugin was installed, Nagios was not reloaded, and
discovery was not started.

The tester must privately populate ${ENV_FILE} if it is empty. Then hand control
to the AI. The AI should source that file with tracing disabled and run:

  cd ${HARNESS_DIR}
  set +x
  source ${ENV_FILE}
  /opt/pinpoint/venv/bin/python runner/run_tests.py --config ${LAB_CONFIG} preflight

The AI must stop after preflight and report readiness before conducting tests.
EOF
