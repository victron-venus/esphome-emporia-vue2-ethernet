# Repository maintenance

## Ownership

The public GitHub repository and its settings are managed by [terraform-github-victron](https://github.com/4alvit/terraform-github-victron). The repository definition is `local.repositories.esphome_emporia_vue2_ethernet`; do not create another Terraform state for the same GitHub repository.

Documentation, diagrams and examples are versioned here with Git. Terraform state, saved plans and infrastructure credentials are not repository content.

## Documentation and example checks

```sh
python3 -m pip install -r requirements-checks.txt
python3 scripts/check.py
```

The checks parse JSON and YAML, validate local Markdown links and SVG documents, and reject obvious private configuration artifacts. They do not contact a device, upload firmware, or establish hardware safety.

The GitHub Actions workflow runs the same checks with read-only repository permissions. Use the commands in [the firmware guide](../firmware/README.md) for ESPHome schema and build validation. Real board and end-to-end tests are tracked separately in [Verification](verification.md).

## Diagrams

The SVG files in `docs/assets/` are editable source artifacts. Keep text legible at repository display width, use text labels in addition to color, and update the adjacent tables when the design changes. The signal-budget chart counts MCU signal lines only; it is not a bandwidth, latency or performance benchmark.

## Release boundary

This project publishes documentation and configuration templates. A firmware binary is device-specific and must not be presented as ready to flash while pin assignments, flash size, calibration and electrical constraints remain unverified.
