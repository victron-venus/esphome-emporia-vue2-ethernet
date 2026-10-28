"""Exercise the committed Jinja guards; this is not a Home Assistant runtime."""

import math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import yaml

PACKAGE = Path(__file__).resolve().parents[1] / "home-assistant-energy.yaml"
RAW_CIRCUIT = "sensor.vue2_circuit_01_power"
RAW_NET = "sensor.vue2_net_power"


def is_number(value):
    """Match HA's finite-number predicate for entity-state strings."""
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def as_timestamp(value, default=None):
    if isinstance(value, datetime):
        return value.timestamp()
    return default


class DomainStates:
    def __init__(self, states, domain):
        self._states = states
        self._domain = domain

    def __getattr__(self, name):
        return self._states.get(f"{self._domain}.{name}")


class States:
    def __init__(self, states):
        self._states = states

    def __getattr__(self, domain):
        return DomainStates(self._states, domain)

    def __call__(self, entity_id):
        item = self._states.get(entity_id)
        return item.state if item is not None else "unknown"


def state(value="100", unit="W", reported=1000):
    attrs = {"unit_of_measurement": unit} if unit is not None else {}
    timestamp = datetime.fromtimestamp(reported, timezone.utc) if reported is not None else None
    return SimpleNamespace(state=value, attributes=attrs, last_reported=timestamp)


class EnergyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = yaml.safe_load(PACKAGE.read_text())
        cls.block = cls.package["template"][0]
        cls.helpers = {entry["default_entity_id"]: entry for entry in cls.block["sensor"]}
        cls.environment = NativeEnvironment(undefined=StrictUndefined)
        cls.environment.globals.update(is_number=is_number, as_timestamp=as_timestamp)

    def render(self, entity_id, states, now=1000):
        entry = self.helpers[entity_id]
        context = {"states": States(states), "now": lambda: datetime.fromtimestamp(now, timezone.utc)}
        available = self.environment.from_string(entry["availability"]).render(context)
        value = self.environment.from_string(entry["state"]).render(context)
        self.assertIsInstance(available, bool)
        return available, value

    def all_helpers(self, sample, now=1000):
        states = {RAW_CIRCUIT: sample, RAW_NET: sample}
        return [self.render(entity_id, states, now) for entity_id in self.helpers]

    def test_true_zero_remains_available_zero(self):
        for available, value in self.all_helpers(state("0")):
            self.assertTrue(available)
            self.assertEqual(value, 0)

    def test_import_and_export_preserve_direction(self):
        for power, expected in [(125, (125, 0)), (-125, (0, 125))]:
            states = {RAW_NET: state(str(power))}
            actual = []
            for direction in ("import", "export"):
                available, value = self.render(f"sensor.vue2_grid_{direction}_power", states)
                self.assertTrue(available)
                actual.append(value)
            self.assertEqual(tuple(actual), expected)

    def test_negative_consumption_is_invalid_not_silently_clamped(self):
        available, value = self.render("sensor.vue2_circuit_01_valid_power", {RAW_CIRCUIT: state("-1")})
        self.assertFalse(available)
        self.assertIsNone(value)

    def test_invalid_and_nonfinite_states_are_unavailable(self):
        for raw in ["unknown", "unavailable", "", "bad", "nan", "inf", "-inf", "1e999"]:
            with self.subTest(value=raw):
                for available, value in self.all_helpers(state(raw)):
                    self.assertFalse(available)
                    self.assertIsNone(value)

    def test_wrong_or_missing_units_are_unavailable(self):
        for unit in ["kW", "Wh", "w", "", None]:
            with self.subTest(unit=unit):
                for available, _ in self.all_helpers(state(unit=unit)):
                    self.assertFalse(available)

    def test_missing_entities_are_unavailable_without_render_errors(self):
        for entity_id in self.helpers:
            available, value = self.render(entity_id, {})
            self.assertFalse(available)
            self.assertIsNone(value)

    def test_missing_old_and_future_source_timestamps_are_unavailable(self):
        for reported in [None, 969, 1001]:
            with self.subTest(reported=reported):
                for available, _ in self.all_helpers(state(reported=reported)):
                    self.assertFalse(available)

    def test_exact_freshness_boundary_and_following_expiry(self):
        for available, _ in self.all_helpers(state(reported=970)):
            self.assertTrue(available)
        for available, _ in self.all_helpers(state(reported=970), now=1000.1):
            self.assertFalse(available)

    def test_frozen_numeric_source_expires_then_new_sample_recovers(self):
        frozen = state("250", reported=1000)
        for available, _ in self.all_helpers(frozen, now=1005):
            self.assertTrue(available)
        for available, _ in self.all_helpers(frozen, now=1036):
            self.assertFalse(available)
        for available, _ in self.all_helpers(state("250", reported=1036), now=1036):
            self.assertTrue(available)

    def test_missing_timestamp_attribute_is_unavailable(self):
        sample = SimpleNamespace(state="100", attributes={"unit_of_measurement": "W"})
        for available, _ in self.all_helpers(sample):
            self.assertFalse(available)

    def test_every_integrator_reads_a_guarded_power_helper(self):
        for integrator in self.package["sensor"]:
            self.assertIn(integrator["source"], self.helpers)
            self.assertEqual(integrator["method"], "left")
            self.assertEqual(integrator["unit_prefix"], "k")
            self.assertEqual(integrator["unit_time"], "h")

    def test_silent_source_expiry_has_a_timer_and_startup_trigger(self):
        triggers = self.block["triggers"]
        self.assertIn({"trigger": "time_pattern", "seconds": "/5"}, triggers)
        self.assertIn({"trigger": "homeassistant", "event": "start"}, triggers)
        state_trigger = next(item for item in triggers if item["trigger"] == "state")
        self.assertEqual(set(state_trigger["entity_id"]), {RAW_CIRCUIT, RAW_NET})


if __name__ == "__main__":
    unittest.main()
