#!/usr/bin/env python3
"""
cisco-config-drift: read-only configuration drift detection for Cisco IOS / IOS-XE.

Modes
  snapshot  Pull running-config from each device and save it as the approved baseline.
  check     Pull running-config and diff it against the saved baseline.
  diff      Offline: diff two saved config files (no device access).

Safety
  Read-only. The only command sent to a device is "show running-config".
  Credentials come from environment variables or an interactive prompt, never from files.

Exit codes: 0 no drift, 1 drift found, 2 error.
"""
import argparse
import csv
import datetime as dt
import difflib
import getpass
import logging
import os
import re
import sys
from pathlib import Path

# EDIT: lines that change on their own and are not real drift
VOLATILE_PATTERNS = [
    r"^! Last configuration change",
    r"^! NVRAM config last updated",
    r"^! No configuration change since last restart",
    r"^Building configuration",
    r"^Current configuration\s*:",
    r"^ntp clock-period",
    r"^\s*$",
]
_VOLATILE = [re.compile(p) for p in VOLATILE_PATTERNS]

log = logging.getLogger("drift")


def normalize(text: str) -> list[str]:
    """Strip volatile lines and trailing whitespace so only meaningful changes remain."""
    lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if any(p.search(line) for p in _VOLATILE):
            continue
        lines.append(line)
    return lines


def diff_configs(baseline: str, current: str, name: str = "device") -> list[str]:
    return list(
        difflib.unified_diff(
            normalize(baseline),
            normalize(current),
            fromfile=f"{name} (baseline)",
            tofile=f"{name} (running)",
            lineterm="",
        )
    )


def changed_lines(diff: list[str]) -> tuple[int, int]:
    """Return (added, removed) counts, ignoring the diff headers."""
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return added, removed


def load_inventory(path: Path) -> list[dict]:
    """CSV columns: name,host,device_type (device_type defaults to cisco_ios)."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("host")]
    for r in rows:
        r["device_type"] = r.get("device_type") or "cisco_ios"
        r["name"] = r.get("name") or r["host"]
    return rows


def get_credentials() -> tuple[str, str]:
    user = os.environ.get("DRIFT_USERNAME") or input("Username: ")
    pwd = os.environ.get("DRIFT_PASSWORD") or getpass.getpass("Password: ")
    return user, pwd


def fetch_running(dev: dict, user: str, pwd: str) -> str:
    from netmiko import ConnectHandler  # lazy import: offline diff needs no dependencies

    params = {
        "device_type": dev["device_type"],
        "host": dev["host"],
        "username": user,
        "password": pwd,
    }
    with ConnectHandler(**params) as conn:
        return conn.send_command("show running-config", read_timeout=120)


def cmd_snapshot(args) -> int:
    user, pwd = get_credentials()
    args.baselines.mkdir(parents=True, exist_ok=True)
    failures = 0
    for dev in load_inventory(args.inventory):
        try:
            cfg = fetch_running(dev, user, pwd)
            (args.baselines / f"{dev['name']}.cfg").write_text(cfg, encoding="utf-8")
            log.info("VERIFY %s baseline saved (%d lines)", dev["name"], len(cfg.splitlines()))
        except Exception as e:  # keep going across devices
            failures += 1
            log.error("%s snapshot failed: %s", dev["name"], e)
    return 2 if failures else 0


def cmd_check(args) -> int:
    user, pwd = get_credentials()
    drifted, errors = 0, 0
    report_dir = args.reports / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for dev in load_inventory(args.inventory):
        base_file = args.baselines / f"{dev['name']}.cfg"
        if not base_file.exists():
            log.warning("%s has no baseline, run snapshot first", dev["name"])
            errors += 1
            continue
        try:
            current = fetch_running(dev, user, pwd)
        except Exception as e:
            log.error("%s check failed: %s", dev["name"], e)
            errors += 1
            continue
        d = diff_configs(base_file.read_text(encoding="utf-8"), current, dev["name"])
        if d:
            drifted += 1
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / f"{dev['name']}.diff").write_text("\n".join(d) + "\n", encoding="utf-8")
            a, r = changed_lines(d)
            log.warning("DRIFT %s: +%d -%d lines", dev["name"], a, r)
        else:
            log.info("VERIFY %s matches baseline", dev["name"])
    if drifted:
        log.warning("Drift reports written to %s", report_dir)
        return 1
    return 2 if errors else 0


def cmd_diff(args) -> int:
    d = diff_configs(
        args.baseline.read_text(encoding="utf-8"),
        args.current.read_text(encoding="utf-8"),
        args.baseline.stem,
    )
    if d:
        a, r = changed_lines(d)
        print("\n".join(d))
        print(f"\nDRIFT: +{a} -{r} lines")
        return 1
    print("No drift.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Read-only Cisco configuration drift detection")
    p.add_argument("--log", type=Path, default=Path("logs/drift.log"))
    sub = p.add_subparsers(dest="mode", required=True)

    for mode in ("snapshot", "check"):
        s = sub.add_parser(mode)
        s.add_argument("--inventory", type=Path, default=Path("inventory.csv"))
        s.add_argument("--baselines", type=Path, default=Path("baselines"))
        if mode == "check":
            s.add_argument("--reports", type=Path, default=Path("reports"))

    s = sub.add_parser("diff")
    s.add_argument("baseline", type=Path)
    s.add_argument("current", type=Path)

    args = p.parse_args(argv)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(args.log, encoding="utf-8"), logging.StreamHandler()],
    )
    try:
        return {"snapshot": cmd_snapshot, "check": cmd_check, "diff": cmd_diff}[args.mode](args)
    except Exception as e:
        log.error("fatal: %s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
