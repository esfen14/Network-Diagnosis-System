#!/usr/bin/env python3
"""
Smoke test for demo_lab.py against the real VirtualBox.

It builds a throwaway demo lab with the real script and VBoxManage, checks the
result, and deletes it. It never installs an OS:

* Stage A runs build-base, create, reset, snapshot and destroy for real, but
  never starts a VM and fakes the steps that need a running guest (SSH).
* Stage B starts two of the empty targets for a few seconds to check start/stop,
  the 127.0.0.1-only NAT forwards and the wall's handling of a guest that does
  not answer. They have no OS, so they only sit at "no bootable medium".

Safety: it refuses to run if any pinpoint-demo-* VM already exists, because its
cleanup deletes the demo VMs. Only pinpoint-demo-* VMs are ever touched.

Usage: python3 smoke_test.py [--no-boot] [--iso PATH]
Exit status 0 when every check passes.
"""
import argparse
import base64
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_lab as d

MIN_BOOT_RAM_MIB = 1600     # two small guests plus headroom
results = []


def check(label, condition, detail=""):
    results.append((label, bool(condition)))
    line = ("  PASS  " if condition else "  FAIL  ") + label
    if not condition and detail:
        line += "  -> " + str(detail)
    print(line, flush=True)


def title(text):
    print("\n==== " + text, flush=True)


def forwards(name):
    rules = []
    for key, value in d.vm_info(name).items():
        if key.startswith("Forwarding("):
            rules.append(value)
    return sorted(rules)


def installer_post_command_ok(vm_folder, public_key):
    """The unattended installer must carry our post-install command intact."""
    scripts = sorted(vm_folder.glob("Unattended-*vboxpostinstall.sh"))
    if not scripts:
        return False
    match = re.search(r"echo ([A-Za-z0-9+/=]{40,}) \| base64 -d \| bash", scripts[0].read_text())
    if not match:
        return False
    decoded = base64.b64decode(match.group(1)).decode()
    return public_key in decoded and "NOPASSWD" in decoded


def stage_a_build_and_create(args):
    base = d.VMS["base"]["name"]
    title("A1. build-base: real createvm / modifyvm / createmedium / unattended (no boot)")
    try:
        d.cmd_build_base(args)
    except SystemExit as stop:
        check("build-base completed", False, "exit " + str(stop.code))
        raise
    check("build-base completed", True)
    info = d.vm_info(base)
    check("snapshot base-ready taken", d.BASE_SNAPSHOT in d.snapshot_names(info), d.snapshot_names(info))
    check("NIC1 is NAT with only the ssh forward on 2200",
          info.get("nic1") == "nat" and forwards(base) == ["ssh,tcp,127.0.0.1,2200,,22"], forwards(base))
    check("boot order is disk, then dvd", info.get("boot1") == "disk" and info.get("boot2") == "dvd")
    leftover = []
    for key, value in info.items():
        if value.lower().endswith(".iso"):
            leftover.append(key + "=" + value)
    check("installer ISO ejected before the snapshot", not leftover, leftover)
    public_key = Path(args.state_dir, "id_ed25519_demo.pub").read_text().strip()
    check("installer script carries the post-install command (key + sudo)",
          installer_post_command_ok(Path(info["CfgFile"]).parent, public_key))

    title("A2. create: one linked clone per target")
    try:
        d.cmd_create(args)
    except SystemExit as stop:
        check("create completed", False, "exit " + str(stop.code))
        raise
    check("create completed", True)
    ports_seen = []
    for key in d.ACTIVE_TARGETS:
        spec = d.VMS[key]
        name = spec["name"]
        vm = d.vm_info(name)
        check(key + ": registered", d.vm_exists(name))
        check(key + ": NIC2 is the lab network", vm.get("nic2") == "intnet" and vm.get("intnet2") == d.LAN_NAME)
        check(key + ": exactly one forward, to its own port",
              forwards(name) == ["ssh,tcp,127.0.0.1," + str(spec["ssh_port"]) + ",,22"], forwards(name))
        ports_seen.append(spec["ssh_port"])
        check(key + ": small (512 MiB, 1 CPU, 8 MiB video)",
              vm.get("memory") == "512" and vm.get("cpus") == "1" and vm.get("vram") == "8",
              (vm.get("memory"), vm.get("cpus"), vm.get("vram")))
        check(key + ": has the demo-ready snapshot", d.DEMO_SNAPSHOT in d.snapshot_names(vm))
        check(key + ": lab MAC readable", bool(re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", d.lan_mac(name))))
    check("management ports are all different", len(set(ports_seen)) == len(ports_seen), ports_seen)
    registered = d.registered_vms()
    check("no Pinpoint VM is created", (d.PREFIX + "-server") not in registered, registered)

    title("A3. create again changes nothing")
    before = sorted(d.registered_vms())
    d.cmd_create(args)
    check("re-running create is a no-op", sorted(d.registered_vms()) == before)


def stage_b_boot(args, real_ssh_run, fake_ssh_run, guard):
    first, last = d.ACTIVE_TARGETS[0], d.ACTIVE_TARGETS[-1]
    names = [d.VMS[first]["name"], d.VMS[last]["name"]]
    ports = [d.VMS[first]["ssh_port"], d.VMS[last]["ssh_port"]]
    title("B. start " + first + " and " + last + " for a few seconds (no OS installed)")
    guard["on"] = False
    d.ssh_run = real_ssh_run           # the wall must meet a real guest that does not answer
    for name in names:
        d.vbox_do(True, "startvm", name, "--type", "headless")
    time.sleep(12)
    check("both report running", d.vm_state(names[0]) == "running" and d.vm_state(names[1]) == "running")
    listening = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
    for port in ports:
        check("host listens on 127.0.0.1:" + str(port), "127.0.0.1:" + str(port) in listening)
    wide = []
    for line in listening.splitlines():
        for port in ports:
            if (":" + str(port) + " ") in line and "127.0.0.1" not in line:
                wide.append(line)
    check("the forwards are bound to 127.0.0.1 only", not wide, wide)
    board = d.build_wall(args)
    print("  ---- wall ----")
    for line in board.splitlines():
        print("  | " + line)
    check("wall lists the two running targets", board.count("running") >= 2)
    check("wall reports an unreachable guest without crashing", "not up yet" in board or "timed out" in board)
    check("wall lists every target", all_targets_listed(board))
    for name in names:
        d.vbox_do(True, "controlvm", name, "poweroff")
    d.ssh_run = fake_ssh_run
    time.sleep(6)
    check("both power off", d.vm_state(names[0]) == "poweroff" and d.vm_state(names[1]) == "poweroff")
    guard["on"] = True


def all_targets_listed(board):
    for key in d.ACTIVE_TARGETS:
        if key not in board:
            return False
    return True


def stage_a_reset_and_snapshot(args):
    title("A4. reset and snapshot")
    try:
        d.cmd_reset(args)
    except SystemExit as stop:
        check("reset completed", False, "exit " + str(stop.code))
        return
    check("reset completed", True)
    for key in d.ACTIVE_TARGETS:
        name = d.VMS[key]["name"]
        check(key + ": poweroff with demo-ready after reset",
              d.vm_state(name) == "poweroff" and d.DEMO_SNAPSHOT in d.snapshot_names(d.vm_info(name)))
    args.vms = [d.ACTIVE_TARGETS[0]]
    try:
        d.cmd_snapshot(args)
        check("snapshot re-take completed", True)
    except SystemExit as stop:
        check("snapshot re-take completed", False, "exit " + str(stop.code))
    check(d.ACTIVE_TARGETS[0] + " keeps demo-ready after the re-take",
          d.DEMO_SNAPSHOT in d.snapshot_names(d.vm_info(d.VMS[d.ACTIVE_TARGETS[0]]["name"])))
    args.vms = []


def main():
    parser = argparse.ArgumentParser(description="Smoke test for demo_lab.py (real VirtualBox, no OS install).")
    parser.add_argument("--iso", default=str(d.DEFAULT_ISO))
    parser.add_argument("--no-boot", action="store_true", help="skip stage B (needs about 1.6 GiB free RAM)")
    options = parser.parse_args()

    existing = []
    for name in d.registered_vms():
        if name.startswith(d.PREFIX + "-"):
            existing.append(name)
    if existing:
        print("Refusing to run: demo VMs already exist (" + ", ".join(existing) + ").\n"
              "This test deletes pinpoint-demo-* VMs when it finishes; run `demo_lab.py destroy --apply` "
              "first if you really want to start over.")
        return 2
    if not Path(options.iso).exists():
        print("Ubuntu ISO not found: " + options.iso + " (use --iso)")
        return 2

    state_dir = tempfile.mkdtemp(prefix="demo-smoke-")
    args = d.build_parser().parse_args(["--state-dir", state_dir, "--iso", options.iso, "status"])
    args.apply = True
    args.gui = False
    args.up = False
    args.yes = True          # the test deletes its own VMs without asking
    args.vms = []
    args.no_colour = True
    d.configure(args)

    # Never boot a VM and fake the guest side, except where stage B says otherwise.
    guard = {"on": True}
    real_vbox_do = d.vbox_do
    real_ssh_run = d.ssh_run
    fake = subprocess.CompletedProcess([], 0, "", "")

    def guarded_vbox_do(apply, *a, check=True):
        if guard["on"] and a and a[0] in ("startvm", "controlvm"):
            print("  (not run) VBoxManage " + " ".join(str(x) for x in a))
            return None
        return real_vbox_do(apply, *a, check=check)

    def fake_ssh_run(*a, **k):
        return fake

    d.vbox_do = guarded_vbox_do
    d.ssh_run = fake_ssh_run
    d.run_script = fake_ssh_run
    d.wait_for_ssh = lambda *a, **k: True
    d.wait_for_state = lambda *a, **k: True

    try:
        stage_a_build_and_create(args)
        if options.no_boot:
            print("\n(stage B skipped: --no-boot)")
        elif d.mem_available_mib() < MIN_BOOT_RAM_MIB:
            print("\n(stage B skipped: only " + str(d.mem_available_mib()) + " MiB free, need " + str(MIN_BOOT_RAM_MIB) + ")")
        else:
            stage_b_boot(args, real_ssh_run, fake_ssh_run, guard)
        stage_a_reset_and_snapshot(args)
    except SystemExit:
        pass
    finally:
        title("CLEANUP: destroy (demo VMs only)")
        guard["on"] = False
        d.vbox_do = real_vbox_do
        try:
            d.cmd_destroy(args)
        except SystemExit as stop:
            print("  destroy exited with " + str(stop.code))
        shutil.rmtree(state_dir, ignore_errors=True)
        left = []
        for name in d.registered_vms():
            if name.startswith(d.PREFIX + "-"):
                left.append(name)
        check("no demo VM left registered", not left, left)
        folders = []
        for folder in d.default_machine_folder().iterdir():
            if folder.name.startswith(d.PREFIX + "-"):
                folders.append(folder.name)
        check("no demo folder left on disk", not folders, folders)
        media = subprocess.run(["VBoxManage", "list", "dvds"], capture_output=True, text=True).stdout
        media += subprocess.run(["VBoxManage", "list", "hdds"], capture_output=True, text=True).stdout
        check("no demo media left registered", d.PREFIX + "-" not in media)

    failed = []
    for label, ok in results:
        if not ok:
            failed.append(label)
    title("RESULT")
    print(str(len(results) - len(failed)) + " passed, " + str(len(failed)) + " failed")
    for label in failed:
        print("  FAILED: " + label)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
