# VM Lab Plan (faithful lane)

Status: **working; NCPA, alerts and the `break` commands not yet run.** Design agreed
2026-10-08. The first end-to-end run passed (create, provision, fresh install of `main`,
healthcheck 59/0, discovery and monitoring of five targets, sync); see
[`docs/test-runs/2026-10-08-vm-lab-first-run/`](../test-runs/2026-10-08-vm-lab-first-run/REPORT.md). Feeds
[`Agent_Workflow_and_CI.md`](../../spec%20files/Agent_Workflow_and_CI.md) (test
environments) and replaces nothing in the Docker lab
([`Local_Lab.md`](../manuals/Local_Lab.md)).

## 1. Why a second lane

The Docker lab is fast but is not the installer's appliance: no systemd, no real
`pinpoint` sudo rules, no DHCP, no NCPA install. The faithful lane runs the real
installer steps on a real Ubuntu 22.04.5 VM and monitors real Ubuntu target VMs.
It is slower, so it is for installer-contract changes, NCPA, and pre-release checks.

## 2. Design

### 2.1 Snapshot below the app

A snapshot of a finished install goes stale: a new migration, environment variable,
sudo rule or Nagios setting can make it test something the code no longer does.
So the snapshot stops before Pinpoint.

| Installer step | Depends on Pinpoint's code? | Where it runs |
|---|---|---|
| install-packages, install-nagios-core, install-nagios-plugins, configure-snmp, configure-nagios | No | Once, then frozen in snapshot `os-nagios-ready` |
| deploy-pinpoint-web, configure-pinpoint-privileges | Yes | On every fresh test |

### 2.2 Modes

| Mode | Command | What it does | Use for |
|---|---|---|---|
| Fresh | `scripts/vmlab fresh [branch]` | Restore the snapshot, start, install the pushed branch with the installer's deploy and privilege steps, run the healthcheck | Anything touching migrations, env vars, permissions, configs, the installer contract |
| Quick | `scripts/vmlab sync [--client]` | Copy the working tree into the running VM, restart Gunicorn; does not run migrations | UI and API fixes during QA |
| Upgrade | A second snapshot holding an older release | Re-run the deploy step on it | Testing the upgrade path; retake only at releases |

The installer's `deploy-pinpoint-web.sh` hardcodes `REPO_URL` and
`REPO_BRANCH="main"`. `vmlab fresh` patches a copy inside the VM; the installer
repository is never modified. The branch must be pushed.

### 2.3 Staleness guard

`provision` writes `/etc/pinpoint-vmlab-stamp` (installer commit and a hash of the
five base steps) before the snapshot. `scripts/vmlab status` compares it with the
current installer repository and warns when the base steps changed, which is the
signal to run `provision --force`.

## 3. Pieces

| Piece | State |
|---|---|
| Targets: `demo/demo_lab.py` (five Ubuntu 24.04 VMs on internal network `pinpoint-demo`, `10.77.0.0/28`; break, fix, load, reset, wall, NCPA login) | Built; `up` verified |
| Appliance VM `pinpoint-appliance` (4 GB, 4 CPUs; NIC 1 NAT with SSH and web port forwards, NIC 2 on `pinpoint-demo`), built by `scripts/vmlab create` from the stock Ubuntu 22.04.5 live-server ISO, unattended | Built and verified. Your existing `pinpoint-demo` VM was left alone |
| `scripts/vmlab`: iso, create, prepare, status, provision, fresh, sync, health, setup-admin, smoke, creds, up, down, revert, targets | `create`, `prepare`, `provision`, `fresh`, `health`, `setup-admin`, `smoke`, `sync` verified. Not run on their own: `status` with a live VM, `sync --client`, `revert`, `up`, `down` |
| `lab/smoke.py`: `--email`, `--password`/`SMOKE_PASSWORD`, `--set-network`, `--expect-ips` | Verified on the appliance and, as a regression, on the Docker lab |
| `lab/vmlab.env.example` | Written |

## 4. Steps to get running

No console steps: everything runs from `scripts/vmlab`, using your local clone of the
installer repository for the setup steps.

1. **Targets.** `python3 demo/demo_lab.py create --apply` (after `build-base`), then
   `scripts/vmlab targets up`.
2. **ISO.** `scripts/vmlab iso` downloads the stock Ubuntu 22.04.5 live-server ISO
   (about 2 GB). The installer's own ISO is not needed: its install screens are
   interactive, and the lab runs the same setup steps itself.
3. **Appliance VM.** `scripts/vmlab create` builds `pinpoint-appliance` with an
   unattended install (10 to 25 minutes): SSH key, passwordless sudo, apt sources and
   `10.77.0.1/28` on NIC 2 are set up for you.
4. **Config (optional).** Copy `lab/vmlab.env.example` to
   `~/.config/pinpoint-vmlab/env`; set `VMLAB_INSTALLER_DIR` to your installer clone to
   test installer edits before pushing them.
5. **Snapshot.** `scripts/vmlab provision` runs installer steps 1 to 5, powers off and
   takes `os-nagios-ready`.
6. **First test.** `scripts/vmlab fresh`, then `scripts/vmlab creds`; sign in once at
   `http://127.0.0.1:18080`. `scripts/vmlab setup-admin` sets a fresh administrator
   password (stored privately, never printed) and `scripts/vmlab smoke` signs in with it.

What is not automated: the installer ISO's own install path (interactive screens, the
late-commands that copy the setup files, the first-boot service and the setup wizard).
Test that by hand with `PinPoint-Installer-v1.1.iso` before a release.

## 5. Risks and unknowns

- **Resolved:** the installer steps ran non-interactively without the setup wizard.
- **Installer steps may prompt or expect the setup wizard's environment (was open; resolved above).** The five
  base steps and the two app steps are run directly over SSH, not through
  `pinpoint-setup.sh`. If one needs input or state the wizard provides, `provision`
  or `fresh` will fail at that step; fix by adapting `vmlab`, not the installer.
- **The deploy step needs internet and GitHub access in the VM** (the NAT NIC) and a
  pushed branch.
- **Unattended install on Ubuntu 22.04.5** follows the recipe `demo_lab.py` proved on
  24.04. VirtualBox's generated installer file could differ for 22.04; `create` stops
  with a clear message if its apt section is not in the expected form.
- **Disk:** the appliance disk is sparse (40 GB maximum); the host is near 90% full.
- **Time:** a fresh install builds the client and installs Python dependencies, so
  expect several minutes. Not yet measured.
- **The administrator password** is generated by the installer; `scripts/vmlab setup-admin`
  replaces it and keeps the new one privately. `smoke.py` stops with a clear message if
  a change is still pending.
- **Disk and RAM:** appliance 4 GB plus five targets at 512 MB each fits in about
  9.6 GB free RAM, with little headroom. Close other VMs.
- **`vmlab sync` does not run migrations or re-run privileges.** Use `fresh` when
  models or the installer contract change.

## 6. Done when

- `scripts/vmlab provision` and `fresh` complete on a clean VM and the healthcheck
  reports 0 failed checks.
- `scripts/vmlab smoke` passes against the five demo targets from a fresh install.
- NCPA deployment to one target succeeds through the wizard, and the run is recorded
  in `docs/test-runs/`.
- `status` correctly warns after the installer's base steps change.
- This plan is folded into a manual (`docs/manuals/`) and closed.
