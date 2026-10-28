#!/usr/bin/env python3
"""Check synthetic ESPHome fixtures in a temporary directory; never upload."""

import argparse
import base64
from dataclasses import dataclass, field
from importlib.metadata import version
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parent
EXPECTED_VERSION = "2026.10.0"
PINS = {"clk": 18, "miso": 19, "mosi": 25, "cs": 33}
VALIDATION_DIRECTORY = "validation"
FIVE_SIGNAL_FIXTURE = "fixture.yaml"
FOUR_SIGNAL_FIXTURE = "fixture-4signal.yaml"
LED_COLLISION_FIXTURE = "fixture-led-collision.yaml"
CONFIG_COMMAND = ("config",)
GENERATE_COMMAND = ("compile", "--only-generate")
COMPILE_COMMAND = ("compile",)
COLLISION_ERROR = "multiple places"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def gpio(value):
    if isinstance(value, dict):
        value = value["number"]
    return int(str(value).removeprefix("GPIO"))


def isolated_environment():
    environment = dict(os.environ)
    # Do not let a developer's build-directory overrides escape the temp tree.
    environment.pop("ESPHOME_BUILD_PATH", None)
    environment.pop("ESPHOME_DATA_DIR", None)
    environment["NO_COLOR"] = "1"
    return environment


@dataclass
class FixtureValidator:
    stage: Path
    api_key: str
    ota_password: str
    environment: dict = field(default_factory=isolated_environment)

    @property
    def directory(self):
        return self.stage / VALIDATION_DIRECTORY

    def prepare_sources(self):
        self.directory.mkdir()
        for source in ROOT.glob("*.package.yaml"):
            shutil.copyfile(source, self.stage / source.name)
        for source in (ROOT / VALIDATION_DIRECTORY).glob("*.yaml"):
            text = source.read_text(encoding="utf-8")
            text = text.replace("REPLACE_WITH_TEMPORARY_BASE64_TEST_KEY", self.api_key)
            text = text.replace("REPLACE_WITH_TEMPORARY_TEST_PASSWORD", self.ota_password)
            (self.directory / source.name).write_text(text, encoding="utf-8")

    def command_arguments(self, name, command, overrides):
        argv = [sys.executable, "-m", "esphome"]
        for key, value in (overrides or {}).items():
            argv.extend(["-s", key, value])
        argv.extend(command)
        if command == CONFIG_COMMAND:
            # Only generated throwaway credentials exist in this directory.
            # Read the effective values in memory; never print config output.
            argv.append("--show-secrets")
        argv.append(str(self.directory / name))
        return argv

    def sanitized_output(self, output):
        safe = output.replace(self.api_key, "<temporary-api-key>")
        safe = safe.replace(self.ota_password, "<temporary-ota-password>")
        safe = safe.replace(str(self.stage), "<temporary-fixture>")
        return "\n".join(safe.splitlines()[-25:])

    def run(self, name, command, overrides=None, expected_failure=None):
        result = subprocess.run(
            self.command_arguments(name, command, overrides),
            capture_output=True, text=True, timeout=1800, env=self.environment,
        )
        output = result.stdout + result.stderr
        if expected_failure is not None:
            require(result.returncode != 0 and expected_failure in output,
                    f"{name}: expected rejection was not observed ({expected_failure})")
            return None
        if result.returncode:
            raise RuntimeError(f"{name}: ESPHome failed\n{self.sanitized_output(output)}")
        return result.stdout

    def config(self, name, overrides=None):
        return yaml.safe_load(self.run(name, CONFIG_COMMAND, overrides))


def check_network(name, config, has_reset):
    eth = config["ethernet"]
    require("wifi" not in config and eth["type"] == "W5500", f"{name}: Ethernet-only W5500 required")
    for signal, expected in PINS.items():
        require(gpio(eth[f"{signal}_pin"]) == expected, f"{name}: {signal} substitution was not applied")
    require(("reset_pin" in eth) == has_reset, f"{name}: unexpected reset configuration")
    if has_reset:
        require(gpio(eth["reset_pin"]) == 23, f"{name}: reset substitution was not applied")
    require("interrupt_pin" not in eth, f"{name}: polling must not also request an interrupt")
    require(eth["polling_interval"] == "10ms", f"{name}: wrong polling interval")
    require(eth["interface"] == "spi3", f"{name}: wrong dedicated SPI interface")


def check_runtime(name, config, validator):
    require(config["esp32"]["framework"]["version"] == "5.5.6", f"{name}: unpinned framework")
    require(config["esp32"]["flash_size"] == "4MB", f"{name}: unexpected synthetic flash size")
    require(config["api"]["reboot_timeout"] == "0s", f"{name}: API reboot policy changed")
    require(config["api"]["encryption"]["key"] == validator.api_key, f"{name}: test API key was not applied")
    require(config["ota"][0]["password"] == validator.ota_password, f"{name}: test OTA password was not applied")
    require(gpio(config["i2c"][0]["sda"]) == 21 and gpio(config["i2c"][0]["scl"]) == 22,
            f"{name}: measurement I2C moved")


def check_freshness(name, config):
    meter = next(item for item in config["sensor"] if item["platform"] == "emporia_vue")
    measurements = [meter["phases"][0]["voltage"], meter["ct_clamps"][0]["power"]]
    for measurement in measurements:
        require(measurement["force_update"], f"{name}: identical fresh samples may be suppressed")
        timeout = measurement["filters"][0]["timeout"]
        require(timeout["timeout"] == "15s", f"{name}: missing bounded measurement timeout")
        require(math.isnan(float(timeout["value"])), f"{name}: stale measurements must become unavailable")


def check_unassigned_pins(validator, name, has_reset):
    signals = list(PINS)
    if has_reset:
        signals.append("reset")
    for signal in signals:
        placeholder = "GPIO_TBD_" + signal.upper()
        validator.run(name, CONFIG_COMMAND, {f"eth_{signal}_pin": placeholder}, expected_failure=placeholder)


def check_fixture(validator, name, has_reset):
    config = validator.config(name)
    check_network(name, config, has_reset)
    check_runtime(name, config, validator)
    check_freshness(name, config)
    validator.run(name, GENERATE_COMMAND)
    check_unassigned_pins(validator, name, has_reset)
    # Exercise an override beyond the fixture's default to detect reversed
    # package/substitution precedence. GPIO32 is only a synthetic test.
    overridden = validator.config(name, {"eth_cs_pin": "GPIO32"})
    require(gpio(overridden["ethernet"]["cs_pin"]) == 32, f"{name}: explicit override was ignored")
    validator.run(name, CONFIG_COMMAND, {"eth_cs_pin": "GPIO21"}, expected_failure=COLLISION_ERROR)
    print(f"PASS {name}: effective configuration, C++ generation, all unassigned pins and override precedence")


def check_led_collision(validator):
    original = (validator.directory / FIVE_SIGNAL_FIXTURE).read_text(encoding="utf-8")
    (validator.directory / LED_COLLISION_FIXTURE).write_text(
        original + "\nstatus_led:\n  pin: GPIO23\n", encoding="utf-8",
    )
    validator.run(LED_COLLISION_FIXTURE, CONFIG_COMMAND, expected_failure=COLLISION_ERROR)
    print("PASS known software collisions: measurement SDA and reset/status LED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true", help="also fully compile the five-signal fixture")
    args = parser.parse_args()
    require(version("esphome") == EXPECTED_VERSION, "Install the exact ESPHome version in firmware/requirements.txt")
    with tempfile.TemporaryDirectory(prefix="vue2-fixture-") as temporary:
        validator = FixtureValidator(
            Path(temporary), base64.b64encode(secrets.token_bytes(32)).decode("ascii"), secrets.token_urlsafe(32),
        )
        validator.prepare_sources()
        check_fixture(validator, FIVE_SIGNAL_FIXTURE, has_reset=True)
        check_fixture(validator, FOUR_SIGNAL_FIXTURE, has_reset=False)
        check_led_collision(validator)
        if args.compile:
            validator.run(FIVE_SIGNAL_FIXTURE, COMPILE_COMMAND)
            print(f"PASS {FIVE_SIGNAL_FIXTURE}: full compilation")
    print("Temporary fixtures removed. No upload or device connection was performed.")


if __name__ == "__main__":
    main()
