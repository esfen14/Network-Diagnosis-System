# Test run: issue-80

| | |
|---|---|
| Date | 2026-10-10 |
| Commit tested | Run A: `f0f934db` (branch `issue-80-email-alert-flag`, before `main` was merged in). Run B: `6c6d0102` (same branch with `main`, including #60, merged in) |
| Plan | none; the finish condition of [#80](https://github.com/esfen14/Pinpoint/issues/80) |
| Tester | Claude Code, with the repository owner reading the receiving mailboxes |
| Environment | Fresh installer-built appliance (`scripts/vmlab create`, `provision`, `fresh`): Ubuntu 22.04.5, Nagios Core 4.5.11, installer `c5cd3de`. A new, isolated VM (own ports, state folder and lab network), so the appliances used for other issues were not touched. Database fresh on both runs. Mail went through the installer's `msmtp` helper to Gmail, from a teammate's test account, to two test addresses. |
| Raw evidence | The lab owner's machine: `~/.local/share/pinpoint-vmlab-80/` (`create.log`, `provision.log`, `fresh.log`, `fresh2.log`) and the Nagios and msmtp logs on the appliance. Not committed. |

## Result

**Overall: Pass.** The per-user email alert setting, its permission and the config rebuild on account changes were observed running on a real appliance, and alert emails for a host and for a service reached the opted-in user only. Two things were not repeated on the merged commit (below), and one check was reported by the tester, not observed by the author.

Totals: Pass 19, Fail 0, Blocked 0, Skipped 2.

Automated suites on the merged commit (not VM cases): `scripts/verify.sh all` passed, with 2277 backend tests (14 skipped), 480 frontend tests, the production build and lint with 0 errors.

## Cases

The two test addresses are called "opted-in" and "opted-out" here. The synthetic host `alert-test-vm` at `192.0.2.10` (a documentation address that cannot be routed) was written through Pinpoint's own config generator, not found by a scan.

### Run A, commit `f0f934db`

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| A1 Fresh install of the branch | Pass | Health check 60 passed, 0 warnings, 0 failed (`fresh.log`) | |
| A2 Migration, column, permission | Pass | Head `a4c8e1f6d392`; `Receive_Email_Alerts` present; `account.alerts` seeded and held by the Administrator role | |
| A3 First-run setup | Pass | `complete-setup` returned 200 with the config applied and a backup stored | |
| A4 Nobody eligible | Pass | Turning off the only user's alerts removed every `define contact` and the contact group from `hosts.cfg`; `nagios -v` 0 errors, 0 warnings | |
| A5 Create an opted-in user | Pass | Config rebuilt in the same request; `hosts.cfg` lists only that contact | |
| A6 Create an opted-out user | Pass | No rebuild (empty `data`); the address is nowhere in `hosts.cfg` | |
| A7 Deactivate, then reactivate | Pass | Contact and group removed on deactivation and restored on reactivation, each without a scan | |
| A8 Setting in the API | Pass | `receive_email_alerts` returned by account info and list | |
| A9 Permission check | Pass | As a user with account view/edit/info but not `account.alerts`: changing the value gave 403 and the stored value was unchanged; resending the current value and omitting the field gave 200; creating with the default gave 201; creating opted-out gave 403 | |
| A10 Apply SMTP settings | Pass | Helper exit 0, `/etc/msmtprc` `root:nagios 640`, the copied file was shredded; emptied again afterwards | |
| A11 Host DOWN then UP | Pass | `HOST NOTIFICATION` for DOWN and UP only to the opted-in address; msmtp `recipients=` showed one address, Gmail `250 2.0.0 OK`; both emails received (tester screenshots, 14:04:09 and 14:04:38 UTC) | |
| A12 Host with no eligible recipient | Pass | Generated host had no `contact_groups` line and no contacts were defined; validated and applied; `nagios -v` 0 errors and 1 warning ("no default contacts"), which does not block the apply | |
| A13 Forced validation failure | Pass | With an invalid object added to an included Nagios file, a contact change returned `config_ok: false` and "Config failed to validate"; `hosts.cfg` checksum unchanged; Nagios stayed active; the setting stayed saved. The included file was restored afterwards | |
| A14 Service CRITICAL then OK | Pass | `check_ssh` enabled through Plugin Manager; `ssh-22-tcp` went CRITICAL HARD on the third passive result; `SERVICE NOTIFICATION` for CRITICAL and OK only to the opted-in address; two sends, both `250 OK`; both emails received (tester, 14:24:22 and 14:24:40 UTC) | |
| A15 Opted-out inbox stays empty | Pass (tester-reported) | The owner ticked this on the issue after looking; the author did not observe the mailbox. The opted-out address appears in no Nagios or msmtp log and no generated config | |

### Run B, commit `6c6d0102` (after merging `main`, which includes #60)

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| B1 Fresh install of the merged branch | Pass | Health check 60 passed, 0 warnings, 0 failed (`fresh2.log`) | |
| B2 Migration chain | Pass | `main` had a second Alembic head, so the email alert migration was moved after #60's. Database reached `a4c8e1f6d392` with both `Check_Interval` and `Receive_Email_Alerts` present; `account.alerts` seeded | |
| B3 Users and contacts | Pass | First-run setup, nobody eligible, create opted-in and opted-out, deactivate and reactivate: same results as A3 to A7 | |
| B4 Generated host block | Pass | The host block carried `check_interval 5` (from #60) and `contact_groups system_users` together; `nagios -v` 0 errors and 0 warnings | |
| B5 Mail on the merged commit | Skipped | Not re-sent; the mail path was covered in A10 to A14 and the merge changed templates and settings, not mail | |
| B6 Permission and failure cases on the merged commit | Skipped | A9 and A13 were not repeated; they are covered by the unit tests, which pass on the merged commit | |

## Deviations from the plan

- No plan existed; the cases follow the finish condition of #80.
- Alerts were driven by passive check results on a synthetic host, not by a real outage or a discovered host. Discovery was not run, to avoid scanning the host LAN.
- `scripts/vmlab setup-admin` could not be used: it looks for the credentials label "Username (email):" but the installer now writes "Username (temporary placeholder email):", and a vmlab config file cannot set `VMLAB_STATE_DIR`. The same steps were done by hand with credentials kept out of the output. In Run A the installer's one-time credentials file was deleted before setup had succeeded, and the one-time placeholder password appeared once in the session output of a diagnostic command. The VM is disposable and the password stopped working when setup completed.
- Run A used the pre-merge commit. The merge with `main` happened afterwards and Run B re-checked what the merge could affect.

## Follow-up

- Defects found (no issue filed yet; to be raised by a person):
  - `scripts/vmlab setup-admin` and `VMLAB_STATE_DIR` as above.
  - Service notification emails show "Host: alias" because the generator writes the literal host alias `alias`. Not changed by #80.
- On a failed apply, a changed email alert setting stays saved while the running config lacks the contact until the next successful rebuild. #60 restores the old value instead. To be decided.
- Cases to repeat in the next run: B5 and B6 on the merged commit if the merge is changed again.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range (the synthetic host uses a documentation address; the test mailbox addresses are not named)
- [x] Evidence is referenced by name and location, not pasted
