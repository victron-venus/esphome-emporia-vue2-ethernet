# Experimental Vue 2 Ethernet firmware packages

These packages add W5500 Ethernet to an existing ESPHome configuration for an Emporia Vue 2. They are software building blocks, **not verified hardware designs**. Keep the stock SAMD09 measurement firmware and the existing I2C connection on GPIO21/22.

Use only one package:

- `ethernet-w5500.package.yaml`: four SPI signals plus a dedicated reset GPIO.
- `ethernet-w5500-4signal.package.yaml`: four SPI signals, requiring a separately verified hardware reset supervisor or power-on-reset circuit. Power and ground are additional connections. A floating reset pin or assumed pull-up does not meet this requirement.

Both packages deliberately contain invalid `GPIO_TBD_*` placeholders. A board-level review must establish actual GPIO assignments, power, isolation, reset timing, and safe physical routing before those placeholders are replaced. Successful validation or compilation cannot establish these conditions.

## Integration

For an existing ESPHome installation, start from its working Vue 2 YAML. For factory firmware, use the upstream [Vue 2 configuration guide](https://emporia-vue-local.github.io/docs/tutorial/configuration/) to build a baseline and assign the actual CTs and phases. Preserve or establish the calibration, CT-to-phase mapping, import/export handling, sensor identifiers, and measurement settings. Do not use the synthetic topology in `validation/` as a device configuration.

Add the selected package to the existing `packages` mapping:

```yaml
packages:
  wired_network: !include ethernet-w5500.package.yaml
```

Set the package's `eth_clk_pin`, `eth_miso_pin`, `eth_mosi_pin`, `eth_cs_pin`, and, where applicable, `eth_reset_pin` substitutions only after checking the actual PCB. Merge existing YAML mappings rather than introducing duplicate top-level keys.

Use the ESP-IDF framework and leave `wifi:` and Wi-Fi-dependent components out of the resulting configuration. Ethernet polling requires ESP-IDF 5.1.4 or newer. The fixtures pin **ESPHome 2026.10.0 and ESP-IDF 5.5.6**; another combination needs its own validation. The package uses a dedicated `spi3` host, an initial SPI clock of 8 MHz, and 10 ms polling. Do not configure `interrupt_pin` with `polling_interval`, or assign another SPI peripheral to the same dedicated host. These initial settings are not evidence of signal integrity.

Keep authenticated access in the device configuration:

```yaml
api:
  reboot_timeout: 0s
  encryption:
    key: !secret api_encryption_key

ota:
  - platform: esphome
    password: !secret ota_password
```

`secrets.example.yaml` contains placeholders, not usable credentials. Create a private `secrets.yaml` with a randomly generated 32-byte Base64 API key and a unique OTA password. Never commit that file. Use the device's established secrets when adapting an existing installation.

The explicit `api.reboot_timeout: 0s` prevents the default periodic restart when no authenticated API client connects for 15 minutes. It does not disable the watchdog, fix a stalled network driver, or retain missed measurements for Home Assistant. Test recovery after network and Home Assistant outages. Do not disable Ethernet as a recovery action without an independently tested way to re-enable it.

A factory-firmware device needs an initial UART installation following the upstream flashing instructions. Before any erase or write, preserve a complete ESP32 flash backup of its detected size, including the partition table and NVS. Keep that backup private: it can contain device-specific credentials. Do not alter the SAMD09 firmware for this Ethernet transport. Disconnect the unit from mains before attaching a UART/USB adapter.

Determine the actual module, flash capacity and partition layout before building a deployable image. The fixture's `esp32dev` board and explicit `4MB` flash are synthetic compiler choices, not identification of every Vue 2. Confirm the selected image and OTA partitions fit the detected flash and preserve a tested UART recovery path. Keep GPIO23 disconnected from W5500 reset while running factory firmware, which may still use it as an LED output.

## Measurement freshness

The pinned measurement component stops publishing when an I2C read fails, a packet is malformed, or a packet is marked already read. Without an explicit timeout, the last numeric value can remain visible while Ethernet and the API stay connected.

For every exposed power or voltage sensor, merge a timeout into its existing filter chain and enable updates for identical fresh readings. The fixtures demonstrate:

```yaml
# Within the appropriate CT's power: mapping, not at the document root.
name: Circuit Power
force_update: true
filters:
  - timeout: 15s
```

Keep calibration and any existing filters. Put the timeout after intentional throttling/aggregation, with a timeout comfortably longer than the longest normal output interval. The timeout's default output is `NaN`, which the ESPHome integration exposes as unavailable; do not set its value to `last` or filter out `NaN`. Verify the actual Home Assistant transition and recovery on a low-voltage test setup.

`force_update` lets Home Assistant record an identical new reading. It does not prove a reading is new. Avoid heartbeat or timer-based republishing of cached numbers: that can make stopped acquisition appear fresh. The timeout detects absent publishes, not a controller repeatedly returning old data as new; sequence progression and plausible response to changing loads remain hardware acceptance checks. An API or Home Assistant outage can also lose history even if measurement continues locally.

## Hardware assumptions that software cannot check

- GPIO21/22 remain connected to measurement I2C. Pins absent from YAML may still have physical connections on the PCB.
- GPIO23 normally drives the status LED. Reusing it requires checking the circuit and physically isolating it where necessary; removing the LED component from YAML is not enough.
- Disabling Wi-Fi does not free GPIO pins because the radio is integrated into the ESP32.
- The four-signal variant needs verified W5500 power-on reset and recovery after both independent W5500 power cycles and ESP32-only resets.
- **The dedicated-reset path has an unresolved timing issue:** the inspected ESP-IDF 5.5.6 driver requests a 100 microsecond reset pulse, while the W5500 datasheet requires at least 500 microseconds. It also has no explicit post-release settling delay. A compliant reset implementation and coordinated startup timing must be designed and verified before hardware use; simply adding a pulse-extending supervisor is not sufficient. See [Reset and startup](../docs/hardware.md#reset-and-startup).
- The Ethernet module's supply demand, signal levels, reset timing, and galvanic isolation need separate verification. Do not connect a network cable to an unverified mains-referenced assembly.

## Compiler fixtures

`validation/fixture.yaml` is **never intended to be flashed**. It uses candidate GPIO18/19/25/33 with GPIO23 as reset, omits the status LED, and includes a minimal synthetic measurement topology. The external component is pinned to `emporia-vue-local/esphome` commit `79e2747371b70370b96ef919f7c1e556f461344a`.

Run the isolated validation command from the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r firmware/requirements.txt
python firmware/validate.py

# Also compile the five-signal fixture; this still does not upload anything.
python firmware/validate.py --compile
```

Python 3.12 is used by CI. The script refuses a different ESPHome version, copies only the required sources into a temporary directory, generates throwaway API/OTA credentials, and removes that directory afterward. The original files never receive credentials. Internet access is needed to install dependencies and retrieve the pinned measurement component and toolchain. Dependency versions transitively selected by the pinned ESPHome package are not a complete dependency lock.

The default command validates both variants, verifies effective pin assignments and the pinned framework, generates C++, and exercises rejection of every unassigned GPIO. It also tests substitution precedence and known software pin collisions. `--compile` adds a full build of the five-signal variant only. Do not run ESPHome `upload` or `run` on either fixture. No fixture represents a complete deployment configuration or a verified wiring map.

Generated `.esphome/` build files and real secrets are excluded from version control. The checks performed with ESPHome 2026.10.0 and pinned ESP-IDF 5.5.6 are:

- Both fixtures passed configuration validation and C++ code generation.
- The included five-signal `validation/fixture.yaml` also passed a **full compilation**, including the pinned measurement component, candidate GPIO18/19/25/33 with GPIO23 reset, encrypted API and password-authenticated OTA. Its source files remained unchanged during the build. Temporary random credentials were supplied only for validation.
- Both fixtures rejected every unassigned GPIO placeholder as expected, and explicit substitutions were checked in the resolved configuration.
- The four-signal fixture has not been fully compiled. Neither fixture has been flashed or tested on hardware.

A successful build does not resolve the reset timing issue above, approve the candidate wiring, or establish measurement accuracy. Validation, code generation, a full compile, and hardware testing are distinct levels of evidence; none should be described as another.

## References

- [ESPHome Ethernet component](https://esphome.io/components/ethernet/)
- [ESPHome API reboot behavior](https://esphome.io/components/api/#configuration-variables)
- [ESPHome sensor timeout filter](https://esphome.io/components/sensor/#timeout)
- [Vue 2 configuration](https://emporia-vue-local.github.io/docs/tutorial/configuration/)
- [Initial flashing instructions](https://emporia-vue-local.github.io/docs/tutorial/flashing/)
- [Pinned measurement component](https://github.com/emporia-vue-local/esphome/tree/79e2747371b70370b96ef919f7c1e556f461344a/esphome/components/emporia_vue)
