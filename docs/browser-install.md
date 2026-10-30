# Browser flashing for a reviewed Vue 2 installation

[ESPHome Web](https://web.esphome.io/) can write a prepared ESP32 factory image
from desktop Chrome or Edge. The USB-connected computer does not need Python or
PlatformIO when ESPHome Device Builder on Home Assistant or another server
compiles the image.

**This repository is not yet a ready-to-flash Ethernet product.** It supplies
experimental W5500 packages, not a complete hardware-validated device image.
The `GPIO_TBD_*` placeholders, reset timing, supply/isolation review, calibration
and CT-to-phase mapping must be resolved for the actual board first. A browser
flasher cannot determine those values or make the retrofit safe.

## Before creating an installable image

Read the [hardware design](hardware.md) and
[firmware integration guide](../firmware/README.md). In particular:

- Preserve the factory SAMD09 measurement firmware and GPIO21/22 measurement bus.
- Start from the device's known-good ESPHome measurement configuration, or follow
  the [upstream Vue 2 configuration guide](https://emporia-vue-local.github.io/docs/tutorial/configuration/).
- Resolve the selected W5500 package's exact GPIOs and hardware reset approach.
  The documented dedicated-reset timing issue remains open; compiler fixtures
  do not establish a working reset circuit.
- Verify the actual ESP32 module, flash size, partition layout, calibration,
  sensor identities, CT mapping, power and isolation. Do not substitute the
  compiler fixture's synthetic `esp32dev`/4 MB choices.
- Keep unique native API and OTA credentials in a private `secrets.yaml`.

Until these conditions are satisfied, use the repository for design and software
validation only. Do not flash `firmware/validation/fixture*.yaml` builds.

## Browser route after the board and configuration are reviewed

1. Put the reviewed device YAML and the chosen W5500 package into ESPHome Device
   Builder on Home Assistant or another server, preserving the package's relative
   path. Keep the compiler versions and framework compatible with the checked
   configuration. See [installing ESPHome](https://esphome.io/guides/installing_esphome/).
2. Choose **Install → Manual download → Factory format** to compile on the server
   and download the merged `.factory.bin` to your browser computer.
3. Before any erase or write, preserve a complete private backup of the ESP32
   flash at its detected size, including its partition table and NVS. Follow the
   upstream hardware programming procedure. A normal browser install does not
   create that backup for you.
4. Disconnect the unit from mains before attaching a suitable UART/USB adapter.
   Use the reviewed programming connections and power arrangement. Do not attach
   the browser computer to a mains-powered or unverified assembly.
5. Open **[ESPHome Web](https://web.esphome.io/)**, select **Connect**, choose the
   adapter, then **Install** your factory image. Review the erase confirmation
   and keep the programming supply stable until the write finishes.
6. Verify boot logs, Ethernet link and authenticated API access on the approved
   bench setup. Then test measurement freshness, calibration and outage recovery
   as described in the [verification guide](verification.md).

If manual address control is required, the
[Espressif browser flasher](https://espressif.github.io/esptool-js/) accepts a
**merged ESP32 factory image at `0x0`**. This does not apply to OTA-only images or
a raw backup with an unverified layout. Do not guess offsets for separate image
parts.

## Downloads and future releases

Source ZIPs and compiler fixtures are not deployable firmware. The project does
not publish a universal Vue 2 Ethernet image or an automated install manifest
because the physical board and final device configuration are not established.

A future install button must name the validated hardware revision and flash
layout, supply a complete firmware image with checksums, and provide a reviewed
onboarding procedure. Public binaries must contain neither private credentials
nor synthetic CT/calibration data. Your own factory image remains private.

## Browser and USB troubleshooting

Use desktop Chrome or Edge on Windows, macOS, or Linux and open
[ESPHome Web](https://web.esphome.io/) directly over HTTPS. The browser must expose the Web Serial API (`navigator.serial`). If it does
not, use a current desktop Chrome or Edge; do not assume mobile/iOS support. The ESP device connects to the
computer running the browser; it does not need to connect to the Home Assistant
server's USB port.

- **No serial port:** use a USB data cable, try a direct USB port, and check that
  the USB-to-serial adapter appears in the operating system. Install the adapter
  manufacturer's CP210x or CH340 driver only if the operating system needs it.
- **Port busy or access denied:** close other browser tabs, serial monitors and
  ESPHome log sessions. On Linux, check your distribution's serial-port group
  permissions and sign in again after changing them; do not run the browser as
  root or make all serial devices world-writable.
- **Cannot connect to the bootloader:** follow the exact board's BOOT/EN procedure.
  For an ESP32 DevKit with those buttons, hold BOOT, briefly press EN/RESET, then
  release BOOT once the flasher connects. Do not short unidentified pins.
- **Write errors:** use a shorter data cable and stable USB power. With a generic
  flasher, reduce the serial baud rate before trying again.
- **Image rejected or repeated resets:** stop and verify the chip family, flash
  capacity, board configuration and factory-image format. Do not try arbitrary
  offsets or erase a working device merely to bypass a mismatch.

## Updates and recovery

Keep the original device configuration and its private secrets alongside a
known-good firmware backup. Initial USB installation and encrypted network OTA
are different transports: choosing a browser flasher does not require enabling
an HTTP server, weakening API authentication, or publishing credentials.

For an already working device, use the project's documented OTA update and
migration procedure with its existing identity and credentials. A full serial
factory installation may replace its partition layout or settings. Back up
first and review any erase option before confirming it.

## Upstream instructions

- [ESPHome Device Builder installation](https://esphome.io/guides/installing_esphome/)
- [ESPHome getting started](https://esphome.io/install/getting-started/)
- [ESPHome Web USB installer](https://web.esphome.io/)
- [Espressif generic browser flasher](https://espressif.github.io/esptool-js/)
