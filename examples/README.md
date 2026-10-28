# Integration examples

Read the [integration guide](../docs/integrations.md) before adapting these files.

- [`victron-ac-loads.json`](victron-ac-loads.json) is a `dbus-emporia-vue` configuration for two Home Assistant power entities in watts. Replace the token, endpoint, entity IDs, and circuit positions. Reserve unique GX device instances. It publishes AC-load monitoring, not an ESS grid meter.
- [`home-assistant-energy.yaml`](home-assistant-energy.yaml) is an optional Home Assistant package, not an ESPHome configuration. It estimates one circuit's energy and optionally separate grid import/export energy. Replace its source IDs (including triggers) and verify units, signs and real sample cadence first. Its guarded power helpers expire original source timestamps after 30 seconds, checked every five seconds. Keep the original ESPHome entities as the GX bridge sources; do not forward the timer-refreshed helper timestamps. Keep cumulative device-side counters instead when they already provide the required energy measurements.

All names, entity IDs, device instances, and credentials are examples. Neither file assigns or validates physical GPIOs. Neither file should be flashed to an ESP32.

## Offline regression checks

From the repository root, install `requirements-checks.txt` and run:

```sh
python -m unittest discover -s examples/tests -v
```

These checks execute the example's Jinja templates with synthetic state objects. They cover invalid values, units, consumption direction, missing/future/stale timestamps, and recovery. They do not replace Home Assistant's configuration check or live acceptance tests. JSON and YAML are examples, not ready-to-install device configurations.
