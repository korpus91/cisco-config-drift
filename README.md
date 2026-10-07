# cisco-config-drift

[![ci](https://github.com/korpus91/cisco-config-drift/actions/workflows/ci.yml/badge.svg)](https://github.com/korpus91/cisco-config-drift/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/cisco-config-drift)](https://pypi.org/project/cisco-config-drift/)

Read-only configuration drift detection for Cisco IOS and IOS-XE. Save an approved baseline of every device's running-config, then check on a schedule and get a clean diff of anything that changed outside change control.

## Why

Unauthorized or forgotten changes are a common root cause of outages and a common audit finding (NIST 800-53 CM-3 and CM-6, CIS Control 4, IEC 62443 SR 7.6). This tool answers "did anything change on the switches since the last approved state?" without touching the devices.

## Safety

- The only command sent to a device is `show running-config`. Nothing is ever pushed.
- Credentials come from the `DRIFT_USERNAME` / `DRIFT_PASSWORD` environment variables or an interactive prompt. They are never written to disk.
- Baselines and reports contain full configurations, which can include secrets. They are git-ignored by default; store them like any other sensitive config backup.

## Install

```bash
pip install -r requirements.txt
cp inventory.example.csv inventory.csv   # then edit
```

`inventory.csv` columns: `name,host,device_type` (Netmiko device type, defaults to `cisco_ios`).

## Usage

```bash
python drift.py snapshot          # save approved baselines to baselines/
python drift.py check             # compare running-config to baseline, diffs go to reports/<timestamp>/
python drift.py diff old.cfg new.cfg   # offline, no device access
```

Volatile lines (timestamps, `Current configuration : N bytes`, `ntp clock-period`) are ignored so only real changes are reported. Extend `VOLATILE_PATTERNS` at the top of `drift.py`.

Exit codes: `0` no drift, `1` drift found, `2` error. That makes it easy to alert from Task Scheduler, cron or CI.

Every run logs to `logs/drift.log` with one `VERIFY` or `DRIFT` line per device.

## Tests

```bash
pip install pytest && python -m pytest
```

## License

MIT. See LICENSE. Security reports: see SECURITY.md.
