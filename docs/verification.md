# Verification plan

This is a prospective acceptance plan for an Ethernet modification of the Emporia Vue 2. **Physical wiring, power, isolation, metering behavior, and long-term operation have not been validated by this project.** Configuration validation or a successful firmware build does not establish any of those properties.

The test counts and durations below are proposed project acceptance targets, not manufacturer specifications or completed test results.

| Gate | Evidence required | What it establishes |
| --- | --- | --- |
| Identify and trace | Actual board revision, continuity checks, documented LED branch | Whether the candidate pins are usable |
| Review the assembly | Power budget, reset circuit, isolation and mounting assessment | Whether bench and line-powered tests may proceed |
| Validate and build | Final configuration, pinned tools, build result and firmware checksum | Software buildability only |
| Exercise the network | Cold-start, software-restart, link, DHCP and OTA results | Recovery on the tested low-voltage assembly |
| Validate metering | Reference comparisons, traffic tests, thermal observations and endurance log | Behavior of the tested line-powered assembly |
| Publish findings | Sanitized evidence with revision and remaining limitations | The exact scope of any validated hardware claim |

All gates below remain to be demonstrated for a physical modification. Do not treat a later gate as a substitute for an earlier one.

## 1. Establish the actual hardware

- Record the PCB revision, ESP32 module marking, detected flash size, W5500 module identity, and module schematic revision. Do not take memory size or module pad numbers from the synthetic fixture.
- Photograph both PCB sides and mark verified solder points without confusing ESP32 GPIO numbers with physical pad numbers.
- With power disconnected, trace each candidate GPIO18/19/25/33/23 to existing circuits. Resolve any uncertainty before assigning it to SPI or reset.
- Verify the GPIO23 LED branch and document its removal or electrical accommodation. Confirm the firmware has no remaining LED or automation use of that pin.
- Confirm GPIO21/22 still connect to the measurement controller, and leave its firmware unchanged. Do not repurpose GPIO26.
- Save a complete factory firmware backup before modification, following the [flashing guidance](https://emporia-vue-local.github.io/docs/tutorial/flashing/). Read the entire detected flash range, record its size and checksum, and verify a second read matches before erasing anything. Keep device-specific backups and credentials private; they do not belong in a public repository. Document the hardware changes that must be reversed before restoring factory firmware, especially GPIO23.

**Pass condition:** the pin map is supported by measurements on the actual revision, not merely by the partial schematic or a compiler accepting GPIO numbers.

## 2. Review power, reset, and mechanical design

Review the [hardware design](hardware.md), then document:

- Supply voltage and current requirements of the entire Ethernet module, regulator capacity, expected dissipation, and startup behavior. Distinguish a carrier-board regulator input from its 3.3 V rail.
- SCSn inactive level and RSTn behavior while the ESP32 starts, resets, or is unpowered.
- Existing module pull resistors, reset supervisor, and possible back-power paths. Define the safe low-voltage supply injection point and return; check both power-up orders and either-side-unpowered states where the proposed circuit permits separate supplies.
- A justified isolation barrier for every path between line-powered electronics and the external connector, including the RJ45 shield and mounting hardware.
- Connector support, strain relief, insulation, clearance, and protection from accidental contact.

**Pass condition:** the proposed assembly has a reviewed power and isolation design before any line-powered test or connection to external network equipment in that state. An Ethernet link on a low-voltage bench is not evidence of electrical safety.

## 3. Validate firmware without uploading

- Pin the ESPHome and external component versions used for the build.
- Replace GPIO placeholders only after the physical pin map is verified.
- Check that the final configuration contains Ethernet, the stock measurement-controller I2C configuration, API/OTA, and required metering definitions.
- Check that it contains no Wi-Fi, fallback access point, captive portal, or competing GPIO23 assignment.
- Select the API restart policy explicitly. If `api.reboot_timeout: 0s` is used, test autonomous recovery; if a nonzero timeout is retained, document the resulting planned restarts and metering gaps. Do not inherit a default and simultaneously promise uninterrupted offline operation.
- Validate and compile the exact final configuration. Record tool versions and the firmware checksum.
- Review boot-time and driver reset behavior for the selected configuration. Resolve the [documented 100-microsecond reset pulse in ESP-IDF 5.5.6](hardware.md#reset-and-startup), which is shorter than the W5500 specification, and verify the delay before SPI access. Record any driver correction or coordinated hardware reset design. The four-signal variant needs its own recovery assessment.

**Pass condition:** the intended configuration validates and compiles with no unexplained pin conflicts. This stage proves software buildability only.

## 4. Test logic and networking on low voltage

Disconnect the board from mains for this stage. Use an appropriate low-voltage bench supply and instruments suitable for that setup. Keep ordinary USB/UART and grounded instruments away from line-powered testing.

1. Check for shorts and incorrect supply polarity before power is applied. Measure startup and steady-state supply voltage at the Ethernet module, including link negotiation and traffic. Confirm idle signal voltages and the absence of harmful back-powering in the reviewed power states.
2. Observe RSTn and SCSn. Confirm reset remains low for at least 500 microseconds, the required post-reset settling interval precedes SPI access, and SCSn is inactive outside transactions. Use the [W5500 reset specification](https://docs.wiznet.io/assets/files/W5500_ds_v110e-226ffec190c588b69f88d629789585e1.pdf).
3. Confirm stable Ethernet link, DHCP addressing, API access, and OTA over Ethernet. Verify the compiled firmware does not start Wi-Fi or an access point.
4. Perform at least 20 cold starts and 20 ESP32 software restarts while leaving the Ethernet module powered for the software-restart cases. Include ESP32 hardware reset, short supply interruptions and slow supply ramps within the reviewed bench setup. Exercise W5500-only restart if the hardware allows it. Every claimed recoverable case should recover connectivity without manual intervention; record variants requiring manual recovery rather than describing them as equivalent.
5. Perform at least 10 cable disconnect/reconnect cycles and several switch restarts. Confirm the device reconnects and resumes reporting. Record recovery time rather than assuming a fixed network-independent deadline.
6. Boot without a connected cable or DHCP service, then restore each. Restart Home Assistant and leave its API connection absent for longer than the configured reboot timeout; for a zero timeout, test at least 20 minutes. Verify the stated reboot policy and eventual recovery, including discovery or reconnection after an IP-address change. Inspect logs for watchdog events and unrecovered Ethernet errors.
7. Perform an OTA update and verify that the replacement firmware boots and remains accessible through Ethernet. Confirm the actual flash/partition layout and a local recovery method first. Test rejection of incorrect API/OTA credentials, and a deliberately interrupted OTA transfer on a recoverable bench unit. An expected update reboot must not be mistaken for continuous measurement.

The following cases require separate evidence; passing one does not establish the others:

| Case | Observe | Failure to rule out |
| --- | --- | --- |
| Both devices cold-start | Rails, RSTn, SCSn, first SPI access | Short reset, premature access, boot-strap interference |
| ESP32 restarts, W5500 remains powered | Repeatable reset/reinitialization and new API connection | A power-on-only reset strategy |
| W5500 restarts while ESP32 stays up | Driver behavior and a documented recovery path | Permanent loss of Ethernet after a peripheral outage |
| Home Assistant or network unavailable | Reboot policy and later reconnection | Reboot loops, stale readings presented as fresh |
| Constant load with unchanged values | Periodic source reports and downstream freshness | Treating lack of value changes as loss of telemetry |
| Update transfer interrupted | Bootable image or verified local recovery | Depending on Ethernet to repair broken Ethernet firmware |

**Pass condition:** all planned cycles recover without manual intervention, voltage stays within component specifications, and there are no unexplained resets or persistent SPI/network errors. Failed cycles require investigation, not averaging into a success rate.

## 5. Validate line-powered operation and metering

This stage requires a reviewed isolation design and suitably qualified personnel, equipment, and procedures. Do not extend the ordinary low-voltage bench connections into a mains test. Use appropriately rated isolated instrumentation and protect external Ethernet equipment until port isolation has been established.

- Record baseline metering behavior and identify a suitable reference instrument and its uncertainty. Use matched load conditions and calibration for comparison. If application firmware or configuration also changed, report that change; a before/after difference cannot automatically be attributed to Ethernet alone.
- Compare voltage, current, and real-power readings under repeatable steady and changing loads. Include low-current operation, where noise changes may be more visible.
- Check every intended current channel and each connected voltage reference. Confirm signs and phase assignments independently of the network interface.
- Repeat relevant measurements with Ethernet idle, with sustained traffic, during cable reconnection, and during API/OTA activity where appropriate. Check for measurement gaps and new electrical noise.
- Verify all intended downstream entities, not just Ethernet reachability: remove a data source in a controlled test and confirm Home Assistant and the GX bridge indicate unavailable data instead of keeping an old value fresh or inventing zero. Confirm recovery, stable entity/service identities and the configured source-age limits.
- Assess supply voltage, component temperatures, reset behavior, and network recovery across the intended installation conditions.
- Run at least 24 hours of representative operation. Record sample continuity, uptime, resets, network errors, and temperatures.

**Pass condition:** the Ethernet modification causes no unexplained metering regression beyond the declared measurement uncertainty, no unexplained persistent reporting gaps, and no violation of component or reviewed safety limits. Record expected reboot/update gaps separately and verify they do not create fabricated energy history. Establish numeric metering tolerances from the chosen reference and intended use before testing; do not infer improved accuracy from Ethernet connectivity.

## 6. Publish evidence and known limits

For each tested revision, publish the verified pin map, module schematic reference, isolation approach, final configuration, tool versions, firmware checksum, and pass/fail results. Separate observed results from proposed improvements and untested variants.

Do not include firmware dumps, credentials, serial numbers, network identifiers, or private installation details. Do not generalize one successful board revision to all Vue 2 hardware. Keep the project's physical-validation status unverified until evidence supports changing it.
