# Integration examples

Read the [integration guide](../docs/integrations.md) before adapting these files.

- [`victron-ac-loads.json`](victron-ac-loads.json) is a `dbus-emporia-vue` configuration for two Home Assistant power entities in watts. Replace the token, endpoint, entity IDs, and circuit positions. Reserve unique GX device instances. It publishes AC-load monitoring, not an ESS grid meter.
- [`home-assistant-energy.yaml`](home-assistant-energy.yaml) is an optional Home Assistant package, not an ESPHome configuration. It estimates one circuit's energy and optionally separate grid import/export energy. Replace its source IDs and verify units and signs first. Keep cumulative device-side counters instead when they already provide the required energy measurements.

All names, entity IDs, device instances, and credentials are examples. Neither file assigns or validates physical GPIOs. Neither file should be flashed to an ESP32.
