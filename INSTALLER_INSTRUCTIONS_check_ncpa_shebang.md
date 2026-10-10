# Installer instruction: make `check_ncpa.py` runnable by Nagios

Written for: the PinPoint Installer maintainer (the installer lives outside this repository).
Tracks: https://github.com/esfen14/Network-Diagnosis-System/issues/45

## 1. The issue

On installer-built appliances (Ubuntu 22.04) every NCPA service is CRITICAL with
`(Return code of 127 is out of bounds)`, even though the NCPA agents are deployed and answer
when queried directly.

Cause:

- The vendored plugin `check_ncpa.py` (NCPA plugin v1.2.5) starts with `#!/usr/bin/env python`.
- Ubuntu 22.04 provides `python3` only. There is no `python` command.
- PinPoint's generated Nagios command runs the file directly:
  `$USER1$/check_ncpa.py -H $HOSTADDRESS$ -P '$ARG1$' -t '$ARG2$' -M '$ARG3$' ...`
  (executable name is set in `server/app/network_discovery/plugin_registry.py`).
  The kernel runs the shebang, `env` fails with `'python': No such file or directory`, and the
  shell reports exit code 127.

Why the installer did not catch it:

- The verify step runs `python3 check_ncpa.py --help`. That bypasses the shebang, so it passes.
- The healthcheck only tests that the file exists and is executable.

Confirmed workaround: `apt install python-is-python3` made all six checks return real values
(CPU 4%, disk 25.9%, memory 50%). We do not recommend it as the fix (see section 2).

## 2. What needs to be fixed

### Fix A — install the plugin with a working interpreter line (required)

When the installer places `check_ncpa.py` in the Nagios plugin directory
(`/usr/local/nagios/libexec/`), rewrite the first line to:

```
#!/usr/bin/env python3
```

- Do it idempotently: only touch line 1 if it names `python` without a `3`.
- Keep the file executable (`0755`), owned by the Nagios plugin owner.
- Do not use `apt install python-is-python3` as the primary fix. It changes the interpreter
  alias for the whole machine. Use it only if you prefer it, and then make Fix B pass for it.
- Do not change the Nagios command to `python3 $USER1$/check_ncpa.py`. PinPoint generates the
  command from its registry and its acceptance plan expects `$USER1$/check_ncpa.py`.

### Fix B — verify the way Nagios runs the plugin (required)

Replace the verify step `python3 check_ncpa.py --help` with a direct execution as the Nagios
user:

```
sudo -u nagios /usr/local/nagios/libexec/check_ncpa.py --help
```

Fail the install, with a message naming the interpreter, if the exit code is non-zero
(127 means a missing interpreter, 126 means a permission problem).

### Fix C — healthcheck must execute, not just stat (required)

The healthcheck for `check_ncpa.py` must run the same direct, as-Nagios-user execution as
Fix B. A file that exists and has the execute bit can still be unrunnable.

### Fix D — generalise (recommended)

For every plugin the installer places, read line 1. If it is a `#!` line, confirm its
interpreter resolves (`command -v`, using the Nagios user's PATH). Report all failures
together at the end of the install.

## 3. Where to fix it

The installer repository (separate from this one). Locate these three places; names will
differ in your tree:

| Change | Look for |
|---|---|
| Fix A | The step that copies or downloads `check_ncpa.py` into `libexec` |
| Fix B | The post-install verify step containing `python3 ... check_ncpa.py --help` |
| Fix C | The healthcheck routine that tests the plugin file's existence and executability |

Nothing is needed in the PinPoint application for this fix.

## 4. Acceptance criteria

On a fresh stock Ubuntu 22.04 install, with no `python` command present:

1. `head -1 /usr/local/nagios/libexec/check_ncpa.py` prints `#!/usr/bin/env python3`.
2. `sudo -u nagios /usr/local/nagios/libexec/check_ncpa.py -H <agent> -P 5693 -t <token> -M cpu/percent`
   returns a real value and exits 0, 1 or 2, never 127.
3. After NCPA is deployed to a device and `check_ncpa` is enabled in Plugin Manager, the
   `ncpa-*` services reach OK or a real threshold state, never "Return code of 127".
4. Negative test: temporarily change line 1 to `#!/usr/bin/env python` and rerun the installer
   verify and healthcheck. Both must fail and name the missing interpreter.
5. Record the commands and results from steps 1 to 4 in the installer's test-run notes.
