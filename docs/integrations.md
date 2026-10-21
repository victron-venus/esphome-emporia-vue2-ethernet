# Home Assistant and Victron integration

Use this local data path after the Vue 2 Ethernet hardware and firmware have passed their acceptance checks:

```text
Vue 2 + W5500
  → Ethernet LAN
  → ESPHome Native API
  → Home Assistant power entities
  → dbus-emporia-vue on the Victron GX
  → individual com.victronenergy.acload services
```

Home Assistant connects directly to the device through the [ESPHome integration](https://www.home-assistant.io/integrations/esphome/). The GX bridge reads those entities from Home Assistant. This path needs no Emporia account, Emporia cloud connection, or MQTT broker. The bridge is a separate project: [dbus-emporia-vue](https://github.com/victron-venus/dbus-emporia-vue).

## Expose measurements in Home Assistant

Keep `api:` enabled in the ESPHome configuration and use an API encryption key stored in `secrets.yaml`. Home Assistant needs the same key. Allow Home Assistant to reach the Vue's Native API port, normally TCP 6053; automatic discovery is optional. Add the device by its LAN address if discovery does not cross network segments. [ESPHome Native API reference](https://esphome.io/components/api/).

In Home Assistant, open **Settings → Devices & services → Add integration → ESPHome**. Check the actual entity IDs in **Developer tools → States**. Names in these examples are placeholders, not IDs that the firmware automatically promises to create.

Before using a power entity:

- Verify its unit is `W`, device class is `power`, and state class is `measurement`.
- Match each CT to the measured voltage phase and verify its direction using a known load. Incorrect phase selection cannot be repaired by renaming an entity.
- Publish periodically, for example every five seconds. Confirm that the entity's `last_reported` advances even for an unchanged reading.
- Disconnect the Vue's network link and confirm that the source eventually becomes unavailable. Do not convert `unknown`, `unavailable`, or a missing reading to zero in a template.

Keep API restart behavior intentional. ESPHome's API `reboot_timeout` defaults to 15 minutes without a client. Setting it to `0s` allows measurement firmware to continue without an API-triggered reboot, but requires testing recovery after Home Assistant and network outages. It does not make Home Assistant receive data while disconnected.

## Publish selected circuits as Victron AC loads

Install the GX bridge using its [installation guide](https://github.com/victron-venus/dbus-emporia-vue/blob/main/docs/installation.md). Use [the example JSON](../examples/victron-ac-loads.json) as the bridge's `config.json`, replacing the endpoint, token, and entity IDs. The Home Assistant source accepts ordinary numeric power entities; an Emporia cloud integration in Home Assistant is not required when ESPHome supplies the measurements. This follows the bridge's [HA state parser](https://github.com/victron-venus/dbus-emporia-vue/blob/main/parse_ha.py).

The example defines two independent circuits. For each channel:

- Keep `id`, `service_name`, and `instance` stable across updates. Choose instances and service names not already used on the GX.
- Point `ha_entity_id` directly to the corresponding ESPHome power entity in watts. Ordinary channels interpret the numeric value as watts; they do not automatically convert `kW`.
- Set `position` from the actual topology: `0` means inverter AC output; `1` means AC input. Both example circuits use `0` and must be changed if that is not their location.
- Keep the token private and restrict the real configuration file to its owner. `ws://home-assistant.local:8123` is a LAN example; use `wss://` when the Home Assistant endpoint provides HTTPS.

The bridge uses Home Assistant WebSocket events and REST reads for quiet-channel freshness checks. A proxy must pass both `/api/websocket` and `/api/states/<entity_id>`. Its default 30-second source-age limit is also explicit in the example. Make it comfortably longer than the actual reporting interval; synchronize the Home Assistant and GX clocks. An old timestamp must not be refreshed by merely fetching the same cached value. See the bridge's [configuration reference](https://github.com/victron-venus/dbus-emporia-vue/blob/main/docs/configuration.md).

After starting the bridge, inspect the first example service on the GX:

```sh
dbus -y com.victronenergy.acload.vue2_circuit_01 / GetItems
```

Confirm `/Connected = 1`, `/Ac/Power` matches the source in watts, and `/DeviceInstance = 71`. A measured zero is valid. After a source disconnect or source-age expiry, expect `/Connected = 0` and unavailable power, not fabricated zero consumption.

This driver mirrors the channel's total power to `/Ac/L1/Power`. That is a representation of one AC load, not a reconstruction of its physical L1/L2/L3 powers. HA-input mode does not forward Home Assistant energy counters; `/Ac/Energy/Forward` remains unavailable. These behaviors are visible in the [bridge implementation](https://github.com/victron-venus/dbus-emporia-vue/blob/main/main.py).

## Keep energy counters in Home Assistant

Power in watts is a rate; energy in kWh is its integral over time. Prefer an existing, validated device-side cumulative energy counter when available. It can continue accounting during a Home Assistant outage if the firmware keeps measuring and retains its counter. Do not integrate an existing kWh entity a second time.

For devices exposing only power, [home-assistant-energy.yaml](../examples/home-assistant-energy.yaml) provides an optional Home Assistant package. It integrates one consumption circuit and, separately, splits a signed net-power entity into grid import and export before integration. Install it only after replacing its source entity IDs. To load it, merge this into the existing `homeassistant:` configuration:

```yaml
homeassistant:
  packages:
    vue2_energy: !include packages/vue2_energy.yaml
```

Save the example package as `packages/vue2_energy.yaml` in the Home Assistant configuration directory. Do not create a second `homeassistant:` key. Run Home Assistant's configuration check before reloading or restarting. [Package configuration](https://www.home-assistant.io/docs/configuration/packages/).

The example uses the integration helper's `left` method, suitable for loads that remain steady and switch abruptly, with `unit_prefix: k` and `unit_time: h` to convert W to kWh. `max_sub_interval` updates the integral while power is constant. Integration is an estimate and cannot recover unobserved changes during missing data. Its accumulated value survives a Home Assistant restart; this does not backfill an outage. [Integration helper](https://www.home-assistant.io/integrations/integration/).

Verify generated entity IDs before relying on the package's internal references. Template `default_entity_id` values apply when entities are first created; an existing registry entry or name collision can give a different ID. Invalid source states make the directional templates unavailable. They deliberately have no `float(0)` fallback. [Template sensors](https://www.home-assistant.io/integrations/template/).

For the Energy dashboard, use energy entities with device class `energy`, unit `kWh`, and a suitable state class (`total` or `total_increasing`). Use power entities only in fields asking for power. Do not relabel watts as kWh or force a signed net-energy total to `total_increasing`. [Home Assistant energy requirements](https://www.home-assistant.io/docs/energy/faq/).

## Signs, topology, and double counting

The optional net-power example assumes **positive = grid import** and **negative = grid export** at one verified grid boundary. It calculates import power as `max(P, 0)` and export power as `max(-P, 0)`, then integrates them separately. If the source uses the opposite convention, correct it before using the package. Do not apply `abs()` to net power: that merges import and export. Splitting signed energy after it has already been integrated also loses the two directional totals.

Add circuit energy to Home Assistant's **Individual devices** section. Add a verified grid-boundary import/export pair to the appropriate grid fields. A downstream circuit is already contained in an upstream whole-house measurement: do not add both as independent grid supplies or sum both into consumption. The same applies to a subpanel total and its included circuits.

Do not feed the bridge's own GX/MQTT output back into its Home Assistant inputs. Use the original ESPHome entities to avoid a feedback loop. Treat duplicate measurements from other meters as cross-checks unless the dashboard's topology explicitly accounts for them.

## AC-load monitoring is not ESS grid feedback

The bridge publishes `com.victronenergy.acload.*`. It does not turn these measurements into a GX grid meter or automatically select them for ESS regulation. Even its optional `submeter` setting keeps the AC-load role. Victron distinguishes consumer AC-load meters from `com.victronenergy.grid`; see the [D-Bus meter model](https://github.com/victronenergy/venus/wiki/dbus#grid-and-genset-and-acload-and-heatpump-meter).

Keep the existing ESS grid-meter configuration. A separate project would be required to validate a supported grid-meter interface, complete phase data, polarity, topology, bounded latency, and loss-of-source behavior for control. This guide configures monitoring only. [Victron ESS grid-meter configuration](https://www.victronenergy.com/media/pg/Energy_Storage_System/en/configuration.html).
