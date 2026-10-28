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

Home Assistant connects directly to the device through the [ESPHome integration](https://www.home-assistant.io/integrations/esphome/). The GX bridge reads those entities from Home Assistant. This path needs no Emporia account, Emporia cloud connection, or MQTT broker. The bridge is a separate project: [dbus-emporia-vue](https://github.com/victron-venus/dbus-emporia-vue). The behavior described below follows [this bridge source revision](https://github.com/victron-venus/dbus-emporia-vue/tree/cac9e2091b262bd3a27b0a3475b210969101fe44); check the installed release before relying on freshness settings or D-Bus paths. This repository does not install or upgrade the bridge.

## Expose measurements in Home Assistant

Keep `api:` enabled in the ESPHome configuration and use an API encryption key stored in `secrets.yaml`. Home Assistant needs the same key. Allow Home Assistant to reach the Vue's Native API port, normally TCP 6053; automatic discovery is optional. Add the device by its LAN address if discovery does not cross network segments. [ESPHome Native API reference](https://esphome.io/components/api/).

In Home Assistant, open **Settings → Devices & services → Add integration → ESPHome**. Check the actual entity IDs in **Developer tools → States**. Names in these examples are placeholders, not IDs that the firmware automatically promises to create.

Before using a power entity:

- Verify its unit is `W`, device class is `power`, and state class is `measurement`.
- Match each CT to the measured voltage phase and verify its direction using a known load. Incorrect phase selection cannot be repaired by renaming an entity.
- Acquire and publish fresh samples periodically, for example every five seconds. Confirm that the original ESPHome entity's `last_reported` advances while a real load stays constant and while it is zero. ESPHome `force_update: true` may be needed to propagate unchanged samples, but it does not acquire measurements by itself. Do not use a heartbeat that simply repeats a cached value to satisfy this test: that would hide a failed measurement controller.
- Disconnect the Vue's network link and confirm that the source eventually becomes unavailable. Do not convert `unknown`, `unavailable`, or a missing reading to zero in a template.

Keep API restart behavior intentional. ESPHome's API `reboot_timeout` defaults to 15 minutes without a client. Setting it to `0s` allows measurement firmware to continue without an API-triggered reboot, but requires testing recovery after Home Assistant and network outages. It does not make Home Assistant receive data while disconnected.

## Publish selected circuits as Victron AC loads

Install the GX bridge using its [installation guide](https://github.com/victron-venus/dbus-emporia-vue/blob/main/docs/installation.md). Use [the example JSON](../examples/victron-ac-loads.json) as the bridge's `config.json`, replacing the endpoint, token, and entity IDs. The Home Assistant source accepts ordinary numeric power entities; an Emporia cloud integration in Home Assistant is not required when ESPHome supplies the measurements. This follows the bridge's [HA state parser](https://github.com/victron-venus/dbus-emporia-vue/blob/cac9e2091b262bd3a27b0a3475b210969101fe44/parse_ha.py).

The example defines two independent circuits. For each channel:

- Keep `id`, `service_name`, and `instance` stable across updates. Choose instances and service names not already used on the GX.
- Point `ha_entity_id` directly to the corresponding ESPHome power entity in watts. Ordinary channels interpret the numeric value as watts without checking its unit; they neither convert nor reject `kW`. Validate units before deployment and after changing source entities. Use a consumption circuit here, not a signed net-grid or generation sensor.
- Set `position` from the actual topology: `0` means inverter AC output; `1` means AC input. Both example circuits use `0` and must be changed if that is not their location.
- Keep the token private and restrict the real configuration file to its owner. `ws://home-assistant.local:8123` is a LAN example; use `wss://` when the Home Assistant endpoint provides HTTPS.

The bridge uses Home Assistant WebSocket events and REST reads for quiet-channel freshness checks. A proxy must pass both `/api/websocket` and `/api/states/<entity_id>`. Its default 30-second source-age limit is also explicit in the example. Make it comfortably longer than the actual reporting interval; synchronize the Home Assistant and GX clocks. An old timestamp must not be refreshed by merely fetching the same cached value. See the bridge's [configuration reference](https://github.com/victron-venus/dbus-emporia-vue/blob/main/docs/configuration.md).

After starting the bridge, inspect the first example service on the GX:

```sh
dbus -y com.victronenergy.acload.vue2_circuit_01 / GetItems
```

Confirm `/Connected = 1`, `/Ac/Power` matches the source in watts, `/DeviceInstance = 71`, and `/LastUpdate` advances only on fresh source reports. A measured zero is valid. After a source disconnect or source-age expiry, expect `/Connected = 0` and unavailable power, not fabricated zero consumption.

This driver mirrors the channel's total power to `/Ac/L1/Power`. That is a representation of one AC load, not a reconstruction of its physical L1/L2/L3 powers. HA-input mode does not forward Home Assistant energy counters; `/Ac/Energy/Forward` remains unavailable. These behaviors are visible in the [bridge implementation](https://github.com/victron-venus/dbus-emporia-vue/blob/cac9e2091b262bd3a27b0a3475b210969101fe44/main.py).

## Keep energy counters in Home Assistant

Power in watts is a rate; energy in kWh is its integral over time. Prefer an existing, validated device-side cumulative energy counter when available. It can continue accounting during a Home Assistant outage if the firmware keeps measuring and retains its counter. Do not integrate an existing kWh entity a second time.

For devices exposing only power, [home-assistant-energy.yaml](../examples/home-assistant-energy.yaml) provides an optional Home Assistant package. It guards one consumption circuit and, separately, splits a signed net-power entity into grid import and export before integration. It requires Home Assistant support for `State.last_reported`. Replace the raw entity IDs everywhere, including the trigger list. The circuit helper rejects negative readings rather than silently treating them as consumption; diagnose the CT direction, calibration or topology instead. To load it, merge this into the existing `homeassistant:` configuration:

```yaml
homeassistant:
  packages:
    vue2_energy: !include packages/vue2_energy.yaml
```

Save the example package as `packages/vue2_energy.yaml` in the Home Assistant configuration directory. Do not create a second `homeassistant:` key. Run Home Assistant's configuration check before reloading or restarting. [Package configuration](https://www.home-assistant.io/docs/configuration/packages/).

The power helpers reject missing/non-numeric/non-finite values, wrong units, missing/future timestamps and original source reports older than 30 seconds. They reevaluate on source changes, Home Assistant startup and a five-second timer. An unchanged numeric source can therefore no longer drive indefinite energy accumulation after its reporting stops. Keep the original ESPHome entities as GX inputs: the scheduled helpers have their own report timestamps and must not replace the original freshness evidence.

The `left` integration method estimates energy for step-like loads; `unit_prefix: k` and `unit_time: h` convert W to kWh. `max_sub_interval` updates the total while a valid power value stays constant; it is **not a freshness timeout**. In the referenced [Home Assistant implementation](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/integration/sensor.py), an unavailable source stops integration and resumption does not reconstruct the missing interval. A valid numeric sample may still be held until the freshness guard expires, normally within 30–35 seconds of its last report. Event-loop delays can make that longer. This estimate is unsuitable for billing or control feedback.

Home Assistant restores the accumulated total after restart, but restored template state and source reconnection are separate concerns. Test startup and reconnection with a known load. Unobserved load changes, rejected samples and outage intervals leave gaps or estimation error; do not promise a continuous counter from this package. Prefer a validated, persistent device-side energy counter if outage accounting is required. [Integration helper](https://www.home-assistant.io/integrations/integration/).

Verify generated entity IDs before relying on the package's internal references. Template `default_entity_id` values apply when entities are first created; an existing registry entry or name collision can give a different ID. Invalid source states make the guarded power templates unavailable. They deliberately have no `float(0)` fallback. [Template sensors](https://www.home-assistant.io/integrations/template/).

For the Energy dashboard, use energy entities with device class `energy`, unit `kWh`, and a suitable state class (`total` or `total_increasing`). Use power entities only in fields asking for power. Do not relabel watts as kWh or force a signed net-energy total to `total_increasing`. [Home Assistant energy requirements](https://www.home-assistant.io/docs/energy/faq/).

## Signs, topology, and double counting

The optional net-power example assumes **positive = grid import** and **negative = grid export** at one verified grid boundary. It calculates import power as `max(P, 0)` and export power as `max(-P, 0)`, then integrates them separately. If the source uses the opposite convention, correct it before using the package. Do not apply `abs()` to net power: that merges import and export. Splitting signed energy after it has already been integrated also loses the two directional totals.

Add circuit energy to Home Assistant's **Individual devices** section. Add a verified grid-boundary import/export pair to the appropriate grid fields. A downstream circuit is already contained in an upstream whole-house measurement: do not add both as independent grid supplies or sum both into consumption. The same applies to a subpanel total and its included circuits.

Do not feed the bridge's own GX/MQTT output back into its Home Assistant inputs. Use the original ESPHome entities to avoid a feedback loop. Treat duplicate measurements from other meters as cross-checks unless the dashboard's topology explicitly accounts for them.

## AC-load monitoring is not ESS grid feedback

The bridge publishes `com.victronenergy.acload.*`. It does not turn these measurements into a GX grid meter or automatically select them for ESS regulation. Even its optional `submeter` setting keeps the AC-load role. Victron distinguishes consumer AC-load meters from `com.victronenergy.grid`; see the [D-Bus meter model](https://github.com/victronenergy/venus/wiki/dbus#grid-and-genset-and-acload-and-heatpump-meter).

Keep the existing ESS grid-meter configuration. A separate project would be required to validate a supported grid-meter interface, complete phase data, polarity, topology, bounded latency, and loss-of-source behavior for control. This guide configures monitoring only. [Victron ESS grid-meter configuration](https://www.victronenergy.com/media/pg/Energy_Storage_System/en/configuration.html).

## Integration acceptance checks

| Case | Required observation |
| --- | --- |
| Constant load and true zero | Raw `last_reported` advances from new device samples; GX stays connected |
| Stop source reports while leaving a numeric state | Guarded HA power expires; GX expires from the original timestamp |
| Missing entity, `unknown`, `unavailable`, NaN or infinity | No fabricated zero; guarded power is unavailable |
| Unit changes to `kW` or a negative consumption reading | Guarded energy input becomes unavailable; fix the mapping before trusting GX |
| Network loss or token revocation | GX power becomes unavailable; correct credentials/reconnect and observe fresh recovery |
| HA restart, template reload or entity rename | No duplicate counter is selected; every integrator points to the intended guarded helper |
| Clock adjustment | Future/old timestamps do not become fresh merely because a poll succeeded |

Run the offline template regression tests with `python -m unittest discover -s examples/tests -v`. They render the actual example templates against synthetic states, including frozen source timestamps. They do not run Home Assistant, the GX bridge, the event scheduler or an electricity meter; complete the live checks before deployment.
