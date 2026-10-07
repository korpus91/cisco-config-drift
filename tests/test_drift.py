import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import drift  # noqa: E402

BASE = """Building configuration...

Current configuration : 1234 bytes
! Last configuration change at 10:00:00 UTC Mon Jan 5 2026
hostname SW1
interface GigabitEthernet1/0/1
 switchport access vlan 10
 spanning-tree portfast
ntp clock-period 36028797018963968
end
"""

SAME_BUT_VOLATILE = BASE.replace("10:00:00", "11:22:33").replace("1234", "1299").replace(
    "36028797018963968", "36028797018963999"
)

CHANGED = BASE.replace("switchport access vlan 10", "switchport access vlan 99")


def test_volatile_lines_are_not_drift():
    assert drift.diff_configs(BASE, SAME_BUT_VOLATILE) == []


def test_real_change_is_drift():
    d = drift.diff_configs(BASE, CHANGED, "SW1")
    assert d
    assert drift.changed_lines(d) == (1, 1)
    assert any("vlan 99" in l for l in d)


def test_offline_diff_exit_codes(tmp_path):
    b = tmp_path / "SW1.cfg"
    c = tmp_path / "SW1-now.cfg"
    b.write_text(BASE)
    c.write_text(SAME_BUT_VOLATILE)
    log = tmp_path / "d.log"
    assert drift.main(["--log", str(log), "diff", str(b), str(c)]) == 0
    c.write_text(CHANGED)
    assert drift.main(["--log", str(log), "diff", str(b), str(c)]) == 1


def test_inventory_defaults(tmp_path):
    inv = tmp_path / "inventory.csv"
    inv.write_text("name,host,device_type\nSW1,192.0.2.10,\n,192.0.2.11,cisco_xe\n")
    rows = drift.load_inventory(inv)
    assert rows[0]["device_type"] == "cisco_ios"
    assert rows[1]["name"] == "192.0.2.11"
