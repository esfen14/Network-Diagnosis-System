# Plan: Real Admin Email on First Login, So SMTP Notifications Can Work

Status: **draft for owner review. Nothing built. Open decisions are in §8.**
Follows the format of `Custom_Checks_Plan.md`; like it, this file is not indexed in
`AGENTS.md`. Behaviour rules move into the specs listed in §9 once decisions are made.

Goal: the first time the installer-created administrator signs in, PinPoint makes them replace
the placeholder email (`admin-xxxx@pinpoint.lan`) with a real, deliverable one. After that the
administrator can configure SMTP, and Nagios notification emails reach a real inbox.

---

## 1. Problem

The installer creates the administrator with a generated placeholder address
(`admin-xxxx@pinpoint.lan`) and runs `flask init-production --admin-email ... --password-stdin`
(`server/app/api/commands/seed.py`, `init_production_command`).

That address is used in three places, and only the placeholder is wrong in all three:

| Use | Where | Effect of a placeholder |
|---|---|---|
| Login name | `User.Email` | Fine. It only has to be unique. |
| Nagios contact | `create_host_cfg.py` ~L506-540 builds one `define contact` per ACTIVE user, `email` = `User.Email`, all in contactgroup `system_users`. Every host and service uses that group. | Nagios runs `notify-host-by-email` / `notify-service-by-email` for an address nobody can read. Mail bounces or is dropped. |
| SMTP test recipient / sender default | Does not exist yet. | Nothing sensible to default to. |

Today there is no way to *require* a real email. The only existing "force" is
`Must_Change_Password` (`system_models.py` ~L77, `login.py` `enforce_password_change`,
`ForcePasswordChange.tsx`). It forces a password change, not an email change, and the
self-service route `POST /api/user/change-password` never touches the email. The only route
that edits an email is the full account-edit route (`management.py` ~L640-700), which needs
`account.edit`, role and status fields, and is built for editing other people.

What is not a problem: validation. `validate_user_email` already rejects malformed addresses
with `check_deliverability=False` (`validation.py` L172), so `.lan` passes. That is also why
validation alone cannot tell a placeholder from a real address.

---

## 2. Design summary

1. **Mark the account**, do not guess from the domain. Add a boolean `Must_Change_Email` to
   `User`, mirroring `Must_Change_Password`. The installer asks `init-production` to set it.
2. **Gate the UI the same way as the password gate.** While the flag is set, the backend
   blocks every API except a short allow-list, and the frontend shows a full-screen
   "Set your email" step instead of the app.
3. **A dedicated, narrow route** changes the signed-in user's own email. It requires the
   current password (the email is the login name) and rejects placeholder domains.
4. **Regenerate the Nagios config** after the change, so the contact carries the real address.
5. **Then, and only then, add SMTP settings** (server, port, TLS, credentials, sender, test
   mail). Notifications stay off until SMTP is configured.

Why a flag and not "email ends in `.pinpoint.lan`": a flag survives an admin who deliberately
keeps a `.lan` address on an internal mail relay, and it also covers future cases (for example
an admin resetting someone's email) without new rules.

---

## 3. Who owns what

| Change | System | Why there |
|---|---|---|
| Generate the placeholder address and pass the "must set email" request | **Installer** (repo-external) | It creates the account. |
| Install and configure a mail transport on the appliance (see Phase 4) | **Installer** | OS packages and root-owned files. |
| `Must_Change_Email` column, migration | **PinPoint server** | Schema is owned by Alembic. |
| `init-production --require-email-change` flag | **PinPoint server** | The installer calls the CLI; it does not touch the database. |
| API gate, `PATCH /api/user/me/email`, `/me` payload | **PinPoint server** | Security rules live in the backend. |
| "Set your email" screen | **PinPoint client** | Same place as `ForcePasswordChange`. |
| Nagios contact regeneration | **PinPoint server** | `regenerate_and_apply_config`. |
| SMTP settings model, API, Settings UI | **PinPoint server + client** | Operator-editable, stored in the database. |
| Writing the SMTP config to the OS transport | **PinPoint server, with an installer-provided privileged helper** | Flask must not run as root (see §6). |
| Specs, tests | **PinPoint repo** | `AGENTS.md` requires spec updates in the same change. |

---

## 4. Phases

Phases 1-3 fix the problem the owner described and are shippable on their own. Phase 4 is the
SMTP work that the fix unblocks. Phase 5 is cleanup.

### Phase 0 - Decisions and confirmation (no code)

Owner: PinPoint maintainer.

- Answer §8 (in particular Q1 skip rule, Q2 how the installer prints the placeholder, Q3 MTA).
- Confirm the Nagios command definitions. `notify-host-by-email` and
  `notify-service-by-email` come from the Nagios sample config, not from PinPoint, and
  `contact_template.cfg.tpl` only names them. Check on an installer-built appliance what
  `$USER5$`/`mail` binary they call, and whether that binary exists. If it does not, Phase 4
  has more work than assumed.
- Read the five specs in §9 before Phase 1.

Exit: decisions recorded in §8; the real mail binary known.

### Phase 1 - PinPoint server: flag, CLI, gate, route

Owner: **PinPoint server**. Needs only Python; no installer change to test.

1. **Schema.** Add `User.Must_Change_Email` (`Boolean`, default false, `server_default=false`)
   and an Alembic migration that chains from the current head (check `server/migrations/versions`
   for the head first; there is already a merge-revision pattern). Existing users get `false`
   so upgrades do not lock anyone out.
2. **CLI.** Add `--require-email-change` (flag) to `init-production`. When set, the created
   administrator gets `Must_Change_Email = True`. Without the flag behaviour is unchanged, so
   existing install scripts keep working. Update the command's docstring example.
3. **Placeholder guard.** Add `validate_not_placeholder_email(email)` in
   `server/app/api/helper/validation.py`. It rejects the reserved placeholder domain
   (`pinpoint.lan`; keep the string in one constant shared with the CLI docstring/tests).
   Rejection message: "Use a real email address; pinpoint.lan is reserved for the installer."
4. **Gate.** Extend `enforce_password_change` in `login.py` (or add a sibling
   `before_app_request`) so that while `Must_Change_Email` is true only these endpoints work:
   `api.user.login`, `api.user.logout`, `api.user.user_permission` (`/me`), and the new
   email route. Return 403 with a message distinct from the password one so the client can
   tell them apart. Password gate wins if both flags are set (password first, then email).
5. **Route.** `PATCH /api/user/me/email`, `@login_required`, body
   `{ "email": str, "current_password": str }`:
   - check `current_password` (same pattern as `change_password`);
   - `validate_user_email`, `validate_not_placeholder_email`, then `normalize_email` and
     `validate_email_available` (409 if taken);
   - set `Email`, clear `Must_Change_Email`, write the audit log when
     `is_audit_logging_enabled()` (record old and new address);
   - commit, then call `regenerate_and_apply_config_status()` (Phase 1 step 6);
   - this route must also work when the flag is *not* set, so the admin can fix a typo later.
     Gate it with `login_required` only; it edits the caller's own row, so no permission.
6. **Nagios regeneration.** The contact is `str(user.Email)` and the contactgroup members are
   the same strings, so a stale config would still mail the placeholder. Call
   `regenerate_and_apply_config_status()` after commit. If regeneration fails, keep the email
   change (the user must not be stuck), return success with a warning field, and log it. Do
   not roll back.
7. **`/me` payload.** Add `must_change_email: bool` next to `must_change_password`
   (`management.py` ~L789).
8. **Existing admin edit route.** When an admin changes another user's email through the
   full edit route (L676), it should also reject the placeholder domain. It should *not* set
   `Must_Change_Email` (the admin chose that address on purpose).

Exit: unit tests in §7 pass; `flask init-production --require-email-change` creates a gated
admin on a scratch database.

### Phase 2 - PinPoint client: "Set your email" screen

Owner: **PinPoint client**.

1. `CurrentUserContext.tsx`: read `must_change_email` into `mustChangeEmail` (same line as
   `mustChangePassword`, L47).
2. New `ForceEmailChange.tsx` next to `ForcePasswordChange.tsx`; reuse its layout, input class
   and sign-out button. Fields: new email, confirm email, current password. Copy: explain that
   notifications are sent to this address and that it becomes the sign-in name.
3. `AdminLayout.tsx` (L9-18): render order is password gate, then email gate, then the app.
4. After success call `reload()`, then show a one-line notice that the sign-in name changed.
5. Client-side checks only for UX (non-empty, match, looks like an email, not `@pinpoint.lan`).
   The server remains the authority.
6. Add a "Change email" action to the user's own profile area so the admin can change it later
   without the gate. Find the existing profile/menu entry in `Header.tsx` first; if there is
   none, put it on `SettingsPage.tsx` under a new "My account" block and note the new page
   element in `Frontend_Modules_and_Routes.md`.

Exit: component tests in §7 pass; manual run shows the gate, the success path, and sign-out.

### Phase 3 - Installer: request the gate and stop printing a misleading login

Owner: **Installer (repo-external)**. Depends on Phase 1 being released, because the flag
must exist in the PinPoint version being installed.

1. Pass `--require-email-change` when it runs `flask init-production`.
2. Keep generating `admin-xxxx@pinpoint.lan` and the password exactly as today. The
   placeholder must use the domain the server rejects (`pinpoint.lan`), so the two sides
   agree. Put the domain in one installer constant.
3. Gate on version: if the PinPoint being installed predates this feature, the CLI rejects
   `--require-email-change`. Either detect support (`flask init-production --help | grep
   require-email-change`) and skip the flag, or require the matching PinPoint version. Pick
   one in §8 Q4. Do not swallow the error.
4. Final screen / summary file: tell the operator "On first sign-in you will be asked to set
   your real email address; notifications will be sent there." Print the *placeholder* as the
   username they type at first sign-in; the real one replaces it afterwards.
5. Healthcheck: after install, optionally call `flask shell`/a small query that confirms the
   administrator row has `Must_Change_Email = true`. Do not log the password.
6. No installer change touches the database directly; everything goes through the CLI.

Exit: a clean appliance install lands on the "Set your email" screen at first sign-in, and
after the change the Nagios contact file contains the real address (check
`/usr/local/nagios/etc/...` generated host config for the contact line).

### Phase 4 - SMTP configuration (unblocked by Phases 1-3)

Owner: **PinPoint server + client, plus the installer for the OS side.**
Transport decided (Q3): **msmtp**. Mail provider decided (Q9): **Gmail** with an app password; OAuth is out of scope.

Background to verify in Phase 0: Nagios does not speak SMTP. Its email commands pipe a message
to a local mail program, so "configuring SMTP" really means configuring that program (for
example `msmtp` as a relay client) and making sure Nagios' commands call it.

A. **Installer** installs the chosen transport (decided: `msmtp-mta` plus `bsd-mailx`, a send-only relay
   client with no listening daemon; do not install `mailutils`, which can pull in Postfix) and creates an empty, root-owned config the PinPoint
   helper is allowed to replace. It also provides the privileged helper from step D.

B. **PinPoint server: model and API.**
   - `SMTP_SETTINGS` singleton table (or columns on `SYSTEM_SETTINGS`; prefer a new table so
     the credential column is isolated): host, port, TLS mode (none / STARTTLS / SSL), username,
     encrypted password, sender address, `Updated_At`, `Updated_By`, `Version` for optimistic
     concurrency like `SystemSettings`.
   - Permission: reuse `settings.system` or add `settings.smtp` (Q5). If added, add it to
     `PERMISSIONS` in `seed.py`; `sync-permissions` already grants new permissions to
     Administrator on upgrade.
   - Routes: `GET`/`PUT /api/system/smtp-settings`, `POST /api/system/smtp-settings/test`.
   - The password is write-only: never returned by GET, stored encrypted (see how the custom
     check passwords were stored in `Custom_Checks_Plan.md` and reuse that mechanism).
   - Test route sends one message to the signed-in user's own (now real) email and returns the
     transport's error text, trimmed.

C. **PinPoint client:** an "Email (SMTP)" card on `SettingsPage.tsx` with the fields above, a
   "Send test email" button, and a disabled state with an explanation while the signed-in
   user's email is still a placeholder (belt and braces; the gate should prevent it).

D. **Applying the config to the OS.** Flask runs unprivileged. Use a narrow, root-owned helper
   (script or sudoers entry limited to one command) that takes the settings on stdin and
   rewrites the transport config. The installer ships and permissions it. PinPoint calls it
   after a successful save. Do not give the Flask user write access to `/etc`.

E. **Notifications switch.** `SystemSettings.Notifications` already exists. Decide whether
   Nagios notifications stay disabled until SMTP is saved and tested (recommended, Q6) so the
   appliance does not silently queue mail that can never send.

Exit: a test email arrives from a fresh appliance after the operator fills the card in; a
forced Nagios notification arrives at the admin's real address.

### Phase 5 - Specs, status, cleanup

Owner: **PinPoint repo**, in the same changes as the code.

- Update the specs in §9.
- `Implementation_Status.md`: record Phases 1-3 as done, Phase 4 as gap or done.
- Remove any scratch code; ensure the installer instruction file (see
  `INSTALLER_INSTRUCTIONS_check_ncpa_shebang.md` for the format used) is written for the
  installer maintainer: `INSTALLER_INSTRUCTIONS_require_email_change.md`.

---

## 5. Data flow after the fix

```
Installer                       PinPoint server                      Nagios / OS
---------                       ---------------                      -----------
generate admin-xxxx@pinpoint.lan
flask init-production
  --require-email-change   -->  User(Email=placeholder,
                                     Must_Change_Email=True)
first sign-in              -->  /me -> must_change_email: true
                                gate blocks all other APIs
operator submits real email-->  PATCH /api/user/me/email
                                validate, update, clear flag,
                                audit log
                                regenerate_and_apply_config  -->     contact has real email
operator opens Settings   -->   PUT /api/system/smtp-settings
                                helper rewrites transport config -->  msmtp (or chosen MTA)
"Send test email"         -->   POST .../test                   -->    mail reaches inbox
```

---

### 5a. Flowchart

```
                         INSTALLER
                             |
        creates admin-xxxx@pinpoint.lan + password
        flask init-production --require-email-change
                             |
                             v
              USER row: Must_Change_Email = true
                             |
                             v
                   Admin signs in (placeholder)
                             |
                             v
                  GET /me -> must_change_email?
                      /                \
                   no                  yes
                   |                    |
                   v                    v
              Normal app        "Set your email" screen
                                (all other APIs return 403)
                                        |
                                        v
                          Admin enters email, confirm,
                          current password
                                        |
                                        v
                          PATCH /api/user/me/email
                                        |
                                        v
                       <valid and password right and
                        not placeholder and not taken?>
                          /                      \
                        no                       yes
                        |                         |
          400/409, nothing saved,         save Email, clear flag,
          flag stays, admin retries       write audit log, commit
                  |                               |
                  +--> back to screen             v
                                      regenerate Nagios config
                                      (contact = real email)
                                          /            \
                                      fails           ok
                                        |              |
                                 keep change,          |
                                 warn + log            |
                                        \             /
                                         v           v
                                     Admin can use the app
                                                |
                                                v
                              Settings > Email (SMTP) card
                              (Gmail preset + 16-char app password)
                                                |
                                                v
                              PUT /api/system/smtp-settings
                              password encrypted (secrets_store)
                                                |
                                                v
                              privileged helper rewrites /etc/msmtprc
                                                |
                                                v
                              "Send test email" to admin's address
                                       /                 \
                                 error shown         "Did it arrive?"
                                 (fix settings)        /          \
                                                     no           yes
                                                     |             |
                                           Change email       Email_Verified_At set,
                                           (My account)       notifications may be
                                                              turned on (Q6)
                                                                   |
                                                                   v
                                              Nagios -> msmtp -> Gmail -> admin inbox
```

---

## 6. Risks and edge cases

| Risk | Handling |
|---|---|
| Admin "locked out" by a wrong email | Not a lockout, and the admin can try again. The route is not one-shot: if validation fails (bad format, placeholder domain, duplicate, wrong password) nothing is saved, the flag stays set, and the admin retries as often as needed. There is no attempt limit on this route (the app has no lockout mechanism today). After success the admin can change the email again from "My account" (Phase 2 step 6). The real risk is a *well-formed but wrong* address (typo): sign-in works because the admin types the same typo, but notifications go nowhere. The confirm-email field catches most typos; see Q7 for the rest. |
| Nagios config regeneration fails after the email is saved | "Regeneration" means PinPoint rewriting the Nagios config files (`hosts.cfg` with the `define contact` lines) and reloading Nagios; it has nothing to do with the first generated login credentials, which are never re-created. Keep the email change, warn, log. The next regeneration (discovery, user edits) repairs the contact. |
| Placeholder domain chosen as real | Server rejects `pinpoint.lan`, so the two sides cannot drift. |
| Upgrade of an existing install | Migration defaults to `false`; no one is gated. Existing admins who still have a placeholder get a non-blocking banner (Phase 2 optional, Q8). |
| Another user shares the new address | 409 from `validate_email_available`. |
| Flask user cannot write the transport config | msmtp reads its settings from a file such as `/etc/msmtprc`, which only root can write. PinPoint runs as an unprivileged service user, so it cannot save the Settings card straight into that file. Fix: a tiny root-owned helper that does one job (read settings on stdin, validate, rewrite that one file), which Flask may run through a single-command sudoers entry. See §12. |
| Plain-text SMTP password | Encrypted at rest, write-only in the API, never logged, not in audit-log details. |
| `.lan` rejected by newer `email_validator` | Verify against the pinned version in Phase 1 step 3; if rejected, change the placeholder TLD in the installer and server constant together. |
| Multiple administrators | Only the first, installer-created one is gated. Others are created by an admin with a chosen email. |

---

## 7. Tests

Follow `server/tests/README.md`.

Backend (`server/tests/unit`):
- `init-production --require-email-change` sets the flag; without it, flag is false.
- Gate: flagged user gets 403 on a normal route, 200 on `/me`, `logout`, and the email route.
- Password gate takes precedence when both flags are set.
- Email route: wrong password 400; invalid email 400; placeholder domain 400; duplicate 409;
  success clears the flag, updates `Email`, writes an audit entry, triggers regeneration.
- Regeneration failure still returns success with a warning.
- `/me` includes `must_change_email`.
- Admin edit route rejects the placeholder domain.
- Phase 4: settings round-trip never returns the password; test route surfaces transport error.

Frontend (`client/src/test`, Vitest as used by the existing tests):
- Gate renders when `mustChangeEmail` is true and not when false.
- Validation messages, success path reloads the user, API error is shown.
- Settings SMTP card: write-only password field, disabled test button while unsaved.

Installer (manual acceptance on a fresh Ubuntu 22.04 VM):
- Install, sign in with the placeholder, land on the gate, set a real email, confirm the
  generated host config contains the new address.

---

## 8. Open decisions

| # | Question | Recommendation |
|---|---|---|
| Q1 | Can the operator skip the email step? | **Answered (owner): no.** The step is mandatory; a "skip" would re-create today's state. |
| Q2 | How does the operator learn the placeholder username? | The installer prints it once in the final summary and in its summary file, exactly as it prints the password today. |
| Q3 | Which mail transport on the appliance? | **Answered (owner): msmtp**, as a send-only relay client. Phase 0 still confirms what Nagios' commands call. msmtp does not retry; accepted, since Nagios re-sends reminders for open problems (not recovery messages). |
| Q9 | Which mail provider? | **Answered (owner): Gmail.** See §11. |
| Q4 | Installer vs PinPoint version skew | Installer requires the matching PinPoint release and fails loudly; no silent fallback. |
| Q5 | New permission `settings.smtp` or reuse `settings.system`? | New permission, because the page also stores a credential. |
| Q6 | Keep notifications off until SMTP is tested? | Yes. |
| Q7 | Verify the new email with a confirmation link? | **No link.** A link needs working SMTP, and SMTP is configured only after this step, so it cannot be sent at first sign-in. The Gmail app password (§11) is a different thing: it is the SMTP *login* for sending, entered in Phase 4, and does not verify who owns the admin's address. Instead, verify in Phase 4: the "Send test email" goes to the admin's address, and the card then asks "Did it arrive?" with Yes/No. Yes stores `Email_Verified_At`; No sends the admin to "Change email". Until then the Settings card shows "Email not confirmed" and notifications stay off (Q6). |
| Q8 | Banner for already-installed appliances still on a placeholder? | Yes, non-blocking, shown only to users holding `settings.system`. |

---

## 9. Specs to update (per `AGENTS.md`)

- `Backend_Modules_and_Routes.md`: new route, gate, `/me` field, SMTP routes.
- `Data_Model_and_Integrations.md`: `Must_Change_Email`, SMTP table, how Nagios contacts get
  their address, the OS transport and helper.
- `Frontend_Modules_and_Routes.md`: `ForceEmailChange`, Settings SMTP card, profile action.
- `Engineering_Standards.md`: only if a new secret-storage or privileged-helper rule is set.
- `Implementation_Status.md`: status as phases land.
- `INSTALLER_INSTRUCTIONS_require_email_change.md` (new, same style as the NCPA shebang file).

---

## 10. Suggested order of delivery

1. Phase 0 (a day of checking the appliance and answering §8).
2. Phase 1 and Phase 2 together on one branch; they are useless apart.
3. Phase 3 in the installer once the PinPoint release exists.
4. Phase 4 as its own branch after the owner picks the transport.
5. Phase 5 alongside each.

---

## 11. Gmail specifics (Q9)

- Gmail does not accept the account's normal password over SMTP. It needs an **app password**
  (16 characters, generated by Google). That is a stored password, not a one-time code, so
  PinPoint does not need to handle OTP prompts. The Google account must have 2-Step
  Verification turned on to be allowed to create one. The Settings card should say this.
- Settings card preset "Gmail": host `smtp.gmail.com`, port `587`, STARTTLS (or `465`, SSL),
  username = the full Gmail address, password = the app password.
- Gmail rewrites the From address to the authenticated account, so the sender field should
  default to the username and warn if changed.
- Gmail limits sending (about 500 messages/day for personal accounts). Nagios can exceed that
  in a mass outage; note it in the card help text.
- The appliance needs outbound access to `smtp.gmail.com:587`. A "local" network with no
  internet or a blocked port 587 will fail; the test email (Phase 4 B) must show that error
  plainly rather than "failed".
- Google Workspace or Microsoft 365 are not covered. Revisit if either is needed (OAuth).

---

## 12. Why Flask cannot write the transport config, and the helper

- msmtp reads its settings (host, port, user, password) from a file, for example `/etc/msmtprc`.
  Nagios' mail command runs `mail`, which hands the message to msmtp, which reads that file.
- Only root can write under `/etc`. PinPoint runs as an unprivileged service user on purpose, so
  a bug or exploit in the web app must not become root.
- So saving the SMTP card in the database is not enough; the file msmtp reads must change too.
- The installer ships a small root-owned script (for example `/usr/local/sbin/pinpoint-apply-smtp`)
  and a sudoers line that lets the PinPoint user run only that script, nothing else.
- Flask pipes the settings to the script on stdin (never on the command line, where `ps` could
  show the password). The script validates the fields, writes the file with mode `600`, and exits
  non-zero with a short message on failure, which PinPoint shows in the card.
- Because msmtp reads the password from that file, the app password also exists in plain text
  there. The encrypted copy in the database is what PinPoint re-applies from; the file must be
  `600` and owned by the account that runs the mail command. Confirm in Phase 0 which account
  that is (Nagios runs it, so the file may need to be readable by `nagios`).

## 13. Database readiness

Checked against `server/app/system_models.py` and `server/app/secrets_store.py`.

- **The placeholder is replaced in place.** It is the `USER.Email` value on the admin's existing
  row (unique, indexed, 120 chars). `PATCH /api/user/me/email` updates that row; no second user
  is created and `UserID` does not change, so role, logs and audit history stay attached.
- **No existing table can hold SMTP credentials.** `SSH_CREDENTIALS` stores only the SSH port,
  key-installed flag and key fingerprint, per discovered device. `USER` stores only the login
  password hash. So Phase 4 needs a new table (`SMTP_SETTINGS`, as §4 B says).
- **Encryption already exists.** `secrets_store.encrypt()/decrypt()` (Fernet, key derived from
  `PINPOINT_SECRETS_KEY` or `SECRET_KEY`) was built for custom-check passwords. `SMTP_SETTINGS`
  should store the app password with it. Limitation to accept: if the key changes, the stored
  password is unreadable and the admin must re-enter it; with a temporary debug key, nothing is
  stored.
- **Schema changes needed, all additive (existing rows unaffected):**
  1. `USER.Must_Change_Email` (Boolean, default false) - Phase 1.
  2. `USER.Email_Verified_At` (nullable DateTime) - for the Q7 "Did it arrive?" step.
  3. New `SMTP_SETTINGS` table - Phase 4.
  Each ships as an Alembic migration chained from the current head. Nothing exists yet for any of
  these, so the database is **not** ready until those migrations are written; Phase 1 does the
  first two.
- **Upgrade safety.** New columns default to false/null, so installed appliances are not gated.
