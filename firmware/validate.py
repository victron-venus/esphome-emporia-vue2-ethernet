#!/usr/bin/env python3
"""Check synthetic ESPHome fixtures in a temporary directory; never upload."""

import argparse
import base64
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


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def gpio(value):
    if isinstance(value, dict):
        value = value["number"]
    return int(str(value).removeprefix("GPIO"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true", help="also fully compile the five-signal fixture")
    args = parser.parse_args()
    require(version("esphome") == EXPECTED_VERSION, "Install the exact ESPHome version in firmware/requirements.txt")

    api_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    ota_password = secrets.token_urlsafe(32)
    environment = dict(os.environ)
    # Do not let a developer's build-directory overrides escape the temp tree.
    environment.pop("ESPHOME_BUILD_PATH", None)
    environment.pop("ESPHOME_DATA_DIR", None)
    environment["NO_COLOR"] = "1"
    with tempfile.TemporaryDirectory(prefix="vue2-fixture-") as temporary:
        stage = Path(temporary)
        (stage / "validation").mkdir()
        for source in ROOT.glob("*.package.yaml"):
            shutil.copyfile(source, stage / source.name)
        for source in (ROOT / "validation").glob("*.yaml"):
            text = source.read_text(encoding="utf-8")
            text = text.replace("REPLACE_WITH_TEMPORARY_BASE64_TEST_KEY", api_key)
            text = text.replace("REPLACE_WITH_TEMPORARY_TEST_PASSWORD", ota_password)
            (stage / "validation" / source.name).write_text(text, encoding="utf-8")

        def run(name, command, overrides=None, expected_failure=None):
            argv = [sys.executable, "-m", "esphome"]
            for key, value in (overrides or {}).items():
                argv.extend(["-s", key, value])
            argv.extend(command)
            if command == ["config"]:
                # Only generated throwaway credentials exist in this directory.
                # Read the effective values in memory; never print config output.
                argv.append("--show-secrets")
            argv.append(str(stage / "validation" / name))
            result = subprocess.run(argv, capture_output=True, text=True, timeout=1800,
                                    env=environment)
            output = result.stdout + result.stderr
            if expected_failure is not None:
                require(result.returncode != 0 and expected_failure in output,
                        f"{name}: expected rejection was not observed ({expected_failure})")
                return None
            if result.returncode:
                safe = output.replace(api_key, "<temporary-api-key>").replace(ota_password, "<temporary-ota-password>")
                safe = safe.replace(str(stage), "<temporary-fixture>")
                raise RuntimeError(f"{name}: ESPHome failed\n" + "\n".join(safe.splitlines()[-25:]))
            return result.stdout

        for name, has_reset in [("fixture.yaml", True), ("fixture-4signal.yaml", False)]:
            config = yaml.safe_load(run(name, ["config"]))
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
            require(config["esp32"]["framework"]["version"] == "5.5.6", f"{name}: unpinned framework")
            require(config["esp32"]["flash_size"] == "4MB", f"{name}: unexpected synthetic flash size")
            require(config["api"]["reboot_timeout"] == "0s", f"{name}: API reboot policy changed")
            require(config["api"]["encryption"]["key"] == api_key, f"{name}: test API key was not applied")
            require(config["ota"][0]["password"] == ota_password, f"{name}: test OTA password was not applied")
            require(gpio(config["i2c"][0]["sda"]) == 21 and gpio(config["i2c"][0]["scl"]) == 22,
                    f"{name}: measurement I2C moved")
            meter = next(item for item in config["sensor"] if item["platform"] == "emporia_vue")
            measurements = [meter["phases"][0]["voltage"], meter["ct_clamps"][0]["power"]]
            for measurement in measurements:
                require(measurement["force_update"], f"{name}: identical fresh samples may be suppressed")
                require(measurement["filters"][0]["timeout"]["timeout"] == "15s",
                        f"{name}: missing bounded measurement timeout")
                require(math.isnan(float(measurement["filters"][0]["timeout"]["value"])),
                        f"{name}: stale measurements must become unavailable")

            run(name, ["compile", "--only-generate"])
            for signal in [*PINS, *(["reset"] if has_reset else [])]:
                placeholder = "GPIO_TBD_" + signal.upper()
                run(name, ["config"], {f"eth_{signal}_pin": placeholder}, expected_failure=placeholder)
            # Exercise an override beyond the fixture's default to detect reversed
            # package/substitution precedence. GPIO32 is only a synthetic test.
            overridden = yaml.safe_load(run(name, ["config"], {"eth_cs_pin": "GPIO32"}))
            require(gpio(overridden["ethernet"]["cs_pin"]) == 32, f"{name}: explicit override was ignored")
            run(name, ["config"], {"eth_cs_pin": "GPIO21"}, expected_failure="multiple places")
            print(f"PASS {name}: effective configuration, C++ generation, all unassigned pins and override precedence")

        collision = stage / "validation" / "fixture-led-collision.yaml"
        collision.write_text((stage / "validation" / "fixture.yaml").read_text() +
                             "\nstatus_led:\n  pin: GPIO23\n", encoding="utf-8")
        run(collision.name, ["config"], expected_failure="multiple places")
        print("PASS known software collisions: measurement SDA and reset/status LED")

        if args.compile:
            run("fixture.yaml", ["compile"])
            print("PASS fixture.yaml: full compilation")
    print("Temporary fixtures removed. No upload or device connection was performed.")


if __name__ == "__main__":
    main()
