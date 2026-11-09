#!/usr/bin/env python3
"""Pure-logic selftest for the boiler-status template logic.

Two things are exercised against a fake HA state table, with NO running Home
Assistant required:

1. custom_templates/boiler_monitoring.jinja's boiler_word() macro — the five
   status rules, asserted to fire in the documented order.
2. packages/boiler_monitoring.yaml's own `attributes:` templates (band_delta,
   minutes_since_fired, due_in_minutes, progress) — rendered through REAL,
   UN-STUBBED Jinja2 `min`/`max`/`round` filters, deliberately. An earlier
   version of this file replaced `min`/`max` with non-standard
   `lambda v, floor: max(v, floor)`-style stubs "to make the tests pass" —
   which hid a real bug: Jinja2's actual `max` filter takes an ITERABLE, not
   a (value, floor) pair, so the shipped `progress` template's
   `(...)|max(0)` raised TypeError against any real Jinja/HA install. Only
   `float`/`as_timestamp`/`states`/`is_state`/`now` are HA-specific and need
   stubbing; `min`/`max`/`round` are core Jinja2 and must stay real, or this
   selftest can pass while the shipped template is broken.

Re-run after any edit to the macro file OR the package's attribute templates.
"""
import datetime
import os
import re
import sys

import jinja2
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(HERE, "..")
MACRO_PATH = os.path.join(REPO_ROOT, "custom_templates", "boiler_monitoring.jinja")
PACKAGE_PATH = os.path.join(REPO_ROOT, "packages", "boiler_monitoring.yaml")


class FakeState:
    def __init__(self, state, last_changed=None):
        self.state = state
        self.last_changed = last_changed


def _ha_globals(state_table, now_ts):
    def states(entity_id):
        s = state_table.get(entity_id)
        return s.state if s is not None else "unknown"

    def is_state(entity_id, value):
        s = state_table.get(entity_id)
        return s is not None and s.state == value

    def as_timestamp(value, default=None):
        if isinstance(value, (int, float)):
            return value
        return default

    def now():
        return datetime.datetime.fromtimestamp(now_ts)

    return dict(states=states, is_state=is_state, as_timestamp=as_timestamp, now=now)


def _float_filter(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def make_env(state_table, now_ts):
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.globals.update(_ha_globals(state_table, now_ts))
    # Only the HA-specific `float` filter is stubbed. min/max/round are real
    # Jinja2 builtins — see module docstring for why that distinction matters.
    env.filters["float"] = _float_filter
    src = open(MACRO_PATH, encoding="utf-8").read()
    tmpl = env.from_string(src + "\n{{ boiler_word() }}")
    return env, tmpl


# ANCHOR is an arbitrary non-zero epoch. 0 is deliberately the sentinel
# as_timestamp() falls back to for "this input_datetime has never been set"
# (a fresh install's helpers start blank) — so `last_fired and (...)` can
# treat it as falsy and skip the refire rules rather than reading epoch-1970
# as a real last-fired time. Using 0 as a REAL anchor in tests would hide
# that behaviour; ANCHOR+delta exercises it the way a live install would.
ANCHOR = 1_700_000_000

BASE = {
    "sensor.boiler_water_temp": "180",
    "sensor.boiler_set_water_temp": "180",
    "sensor.boiler_differential": "20",  # band = 160
    "sensor.boiler_bottom_damper": "0",
    "binary_sensor.boiler_bypass_door_open": "off",
    "binary_sensor.boiler_low_water_alarm": "off",
    "input_number.boiler_hard_floor_temp": "140",
    "input_number.boiler_below_band_watch_offset": "8",
    "input_number.boiler_below_band_hours": "3",
    "input_number.boiler_blower_hours": "3",
    "input_number.boiler_refire_hours": "10",
    "input_datetime.boiler_below_band_since": ANCHOR,
    "input_datetime.boiler_run_started": ANCHOR,
    "input_datetime.boiler_last_fired": ANCHOR,
}


def render(overrides, now_ts):
    table = dict(BASE)
    table.update(overrides)
    state_table = {k: FakeState(v) for k, v in table.items()}
    _, tmpl = make_env(state_table, now_ts)
    out = tmpl.render()
    return out.strip().splitlines()[-1].strip()


CASES = [
    ("bypass open wins over everything else",
     {"binary_sensor.boiler_bypass_door_open": "on",
      "sensor.boiler_water_temp": "90"}, ANCHOR, "bypass_open"),
    ("low water alarm, no bypass",
     {"binary_sensor.boiler_low_water_alarm": "on"}, ANCHOR, "low_water"),
    ("under hard floor (140)",
     {"sensor.boiler_water_temp": "135"}, ANCHOR, "under_floor"),
    ("8 degrees below band (160-8=152) = watch",
     {"sensor.boiler_water_temp": "150"}, ANCHOR, "below_band_watch"),
    ("below band (155 < 160), under 3h = ok (normal dip)",
     {"sensor.boiler_water_temp": "155"}, ANCHOR + 1800, "ok"),
    ("below band (155 < 160), 3h+ = slow recovery",
     {"sensor.boiler_water_temp": "155"}, ANCHOR + 3 * 3600 + 1, "slow_recovery"),
    ("damper on under 3h = ok",
     {"sensor.boiler_bottom_damper": "1"}, ANCHOR + 1800, "ok"),
    ("damper on 3h+ = blower running",
     {"sensor.boiler_bottom_damper": "1"}, ANCHOR + 3 * 3600 + 1, "blower_running"),
    ("refire overdue (>=10h)",
     {}, ANCHOR + 10 * 3600 + 1, "overdue"),
    ("refire 80%+ = fire soon",
     {}, ANCHOR + int(0.85 * 10 * 3600), "fire_soon"),
    ("refire 60%+ = due later",
     {}, ANCHOR + int(0.65 * 10 * 3600), "due_later"),
    ("fresh fire, nothing else wrong = ok",
     {}, ANCHOR + 60, "ok"),
    ("never-fired fresh install (blank helper) does not read as overdue",
     {"input_datetime.boiler_last_fired": "unknown",
      "input_datetime.boiler_run_started": "unknown",
      "input_datetime.boiler_below_band_since": "unknown"}, ANCHOR + 100 * 3600, "ok"),
    ("missing optional low_water_alarm entity never fires",
     {}, ANCHOR, "ok"),
]


def _attribute_templates():
    """Pull the four `attributes:` Jinja blocks out of the live package YAML,
    so this test renders the SAME strings that ship, not a hand-copied
    approximation that can drift out of sync with them."""
    doc = yaml.safe_load(open(PACKAGE_PATH, encoding="utf-8"))
    attrs = doc["template"][0]["sensor"][0]["attributes"]
    return {
        name: attrs[name]
        for name in ("band_delta", "minutes_since_fired", "due_in_minutes", "progress")
    }


# (overrides, now_ts, expected numeric ranges / exact values per attribute)
ATTR_CASES = [
    ("fresh fire just happened -> progress ~0, due_in ~= refire hours",
     {}, ANCHOR + 60, {"progress": (0.0, 0.01), "due_in_minutes": lambda v: v > 590}),
    ("overdue -> progress clamped to 1.0, not above",
     {}, ANCHOR + 50 * 3600, {"progress": (1.0, 1.0)}),
    ("never fired (blank helper) -> progress 0, not an error",
     {"input_datetime.boiler_last_fired": "unknown"}, ANCHOR + 100,
     {"progress": (0.0, 0.0), "minutes_since_fired": None}),
    ("10deg below band (watch_offset=8, so this is in watch territory) -> band_delta=10",
     {"sensor.boiler_water_temp": "150"}, ANCHOR, {"band_delta": (10.0, 10.0)}),
]


def render_attrs(overrides, now_ts):
    table = dict(BASE)
    table.update(overrides)
    state_table = {k: FakeState(v) for k, v in table.items()}
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.globals.update(_ha_globals(state_table, now_ts))
    env.filters["float"] = _float_filter
    macro_src = open(MACRO_PATH, encoding="utf-8").read()
    out = {}
    for name, tmpl_src in _attribute_templates().items():
        rendered = env.from_string(macro_src + "\n" + tmpl_src).render().strip()
        out[name] = rendered
    return out


def _check_attr(name, rendered, check):
    if check is None:
        return rendered in ("None", "none", "")
    if isinstance(check, tuple):
        lo, hi = check
        try:
            v = float(rendered)
        except ValueError:
            return False
        return lo <= v <= hi
    if callable(check):
        try:
            return check(float(rendered))
        except ValueError:
            return False
    return rendered == str(check)


def main():
    failures = []
    for name, overrides, now_ts, expected in CASES:
        got = render(overrides, now_ts)
        status = "OK" if got == expected else "FAIL"
        print(f"[{status}] {name}: expected={expected!r} got={got!r}")
        if got != expected:
            failures.append(name)

    print()
    for name, overrides, now_ts, checks in ATTR_CASES:
        rendered = render_attrs(overrides, now_ts)
        ok = True
        detail = []
        for attr, check in checks.items():
            got = rendered.get(attr)
            passed = _check_attr(attr, got, check)
            ok = ok and passed
            detail.append(f"{attr}={got!r}{'' if passed else ' UNEXPECTED'}")
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {', '.join(detail)}")
        if not ok:
            failures.append(name)

    if failures:
        print(f"\n{len(failures)} FAILED: {failures}")
        return 1
    print(f"\nAll {len(CASES) + len(ATTR_CASES)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
