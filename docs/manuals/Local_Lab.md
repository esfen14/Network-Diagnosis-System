# Local Lab (fast lane)

A disposable Pinpoint appliance and five small servers in Docker, on an
isolated network, for quick QA on your own machine. It starts in about a minute,
resets in seconds, and needs no VirtualBox or installer run.

Use it for UI and API checks, discovery, Nagios config generation and reload,
plugin enablement and alert behavior. Use a real appliance (installer build in a
VM) for anything the container cannot imitate; see [What it cannot test](#what-it-cannot-test).

## Requirements

Docker with Compose v2 and about 4 GB of free RAM and 6 GB of disk for the
images. First build takes 8 to 10 minutes (it compiles Nagios Core 4.5.11 and
plugins 2.4.12, like the installer); later starts reuse the cache.

## Commands

```bash
scripts/lab up          # build if needed, start, wait until the API answers
scripts/lab smoke       # log in, run discovery, wait for 6 hosts up (about 3 min)
scripts/lab ui          # Vite dev server on :5173, proxying /api to the lab
scripts/lab sync        # copy your working tree into the appliance, restart Gunicorn
scripts/lab reset       # throw the appliance away and start fresh
scripts/lab down        # stop and remove the containers
scripts/lab status      # container list
scripts/lab logs [svc]  # follow logs (default: appliance)
scripts/lab shell [svc] # shell in a container
scripts/lab break <target> <ssh|http|snmp|all>   # stop a service or the whole target
scripts/lab fix   <target> <ssh|http|snmp|all>   # start it again
```

Targets: `web01`, `web02`, `app01`, `snmp01`, `legacy01`.

Sign in at the Vite URL (or call the API at `http://127.0.0.1:8000`) with the
seeded development user `admin@test.com` / `Password123!`. The seed also creates
other roles' users with the same password, which is handy for permission checks.
These credentials exist only in the lab.

## The servers

| Target | Address | Runs |
|---|---|---|
| `web01` | 10.78.0.2 | ssh 22, http 80, https 443 (self-signed) |
| `web02` | 10.78.0.3 | ssh 22, http 80 |
| `app01` | 10.78.0.4 | ssh 22, http **8080** |
| `snmp01` | 10.78.0.5 | ssh 22, snmp 161/udp (community `public`) |
| `legacy01` | 10.78.0.6 | ssh on **2222** |

Each target has a `labadmin` user (password `labadmin`, sudo) for NCPA
deployment tests. The appliance is `10.78.0.10`; discovery skips itself.

## Working on the code

1. `scripts/lab up` once.
2. Edit code on your machine. Backend: `scripts/lab sync` copies `server/` into
   the appliance and restarts Gunicorn (databases and generated configs are kept).
   Frontend: `scripts/lab ui` serves `client/` with hot reload against the lab API.
3. `scripts/lab reset` when you want a clean slate.

Your working tree is mounted read-only; the appliance writes its databases and
generated Nagios files inside the container, never into your repository.

## How it matches a real appliance

| Real appliance (installer) | Lab |
|---|---|
| Ubuntu 22.04.5, Nagios Core 4.5.11, plugins 2.4.12, Python 3.14 via uv | Same versions, same install steps |
| Nginx :80 to Gunicorn 127.0.0.1:8000 (1 worker, 4 threads), Apache on 127.0.0.1:8081 | Same layout |
| `/etc/pinpoint/pinpoint.env` with the README settings | Same names, lab values (`lab/appliance/pinpoint.env`) |
| `pinpoint` user, `sudo -n systemctl reload nagios`, `nmap-sudo` | Shims in `lab/appliance/shims/` with the same call shape |
| systemd | supervisord |

Deliberate lab differences:

- **Time runs faster in Nagios.** `interval_length` is 10 seconds instead of 60
  and first checks are not staggered, so results appear in about a minute.
  Behavior that depends on real time (notification intervals, flapping windows)
  will not match production timing.
- **The network is isolated.** The `lab` network is internal and its bridge has
  no address, so discovery sees only the five targets and nothing leaves Docker.
  `PINPOINT_NETWORKS` is `10.78.0.0/24`; never add your real LAN to it.
- Databases are seeded with development data on first start.

## What it cannot test

- The installer and its setup wizard, systemd units, and the real `pinpoint`
  sudo rules.
- DHCP lease changes and device identity across IP changes.
- NCPA installation on a target: the targets have no init system, so treat NCPA
  deployment results here as unverified.
- Performance and scale.

Cover these in the faithful lane: a snapshot of a real installed appliance in a
VM (`server/tests/e2e/network_discovery/`, `demo/`). Record results of any
lab run in [`docs/test-runs/`](../test-runs/README.md).

## Troubleshooting

- **Discovery seems stuck at 0%.** Another host on the scanned network is being
  fingerprinted slowly. Check `docker compose -f lab/compose.yaml exec appliance ps -eo etime,args | grep nmap`.
- **`scripts/lab up` times out.** Run `scripts/lab logs` and look for a Python or
  migration error from the first start.
- **Port 8000 is in use.** Stop whatever holds it, or change the published port in
  `lab/compose.yaml` and pass `--base-url` to `lab/smoke.py`.
- **Disk is filling up.** `docker system df` shows image and cache use.

## Status

Spike. Verified on Docker 29.7 / Compose 5.5: build, start, login, discovery of
all five targets (about 2 minutes), Nagios config validation and reload through
the shim, and `scripts/lab smoke` (9 of 9 checks pass from a fresh reset).
**Not yet verified:** `scripts/lab break` and `fix`, `scripts/lab ui`,
`scripts/lab sync`, plugin enablement with the lab targets, alert behavior, NCPA.
