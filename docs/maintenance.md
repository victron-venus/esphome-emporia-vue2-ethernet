# Repository maintenance

## Ownership

The public GitHub repository and its settings are managed by [terraform-github-victron](https://github.com/4alvit/terraform-github-victron). The repository definition is `local.repositories.esphome_emporia_vue2_ethernet`; do not create another Terraform state for the same GitHub repository.

Documentation, diagrams and examples are versioned here with Git. Terraform state, saved plans and infrastructure credentials are not repository content.

## Documentation and example checks

Use Python 3.12 in an isolated environment for the checked toolchain.

```sh
python3 -m pip install -r requirements-checks.txt
python3 scripts/check.py
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s examples/tests -v
```

Run these commands from a Git checkout. The source check reads tracked files and new nonignored files, so ignored local secrets and generated build trees are not traversed. A private artifact forcibly added to Git still fails validation.

The checks reject duplicate YAML/JSON keys, non-finite JSON numbers, cyclic YAML aliases, symbolic links, and broken local Markdown targets and heading anchors. SVG checks cover explicit scripts and event attributes, external hrefs and ordinary CSS URL references, missing fragment IDs, and basic geometry/accessibility metadata. They do not implement a complete SVG/CSS security model. YAML includes and secrets remain inert. Markdown examples inside code fences are not followed as links. This is a repository source check, not a general-purpose sanitizer or a complete secret scanner.

Regression tests exercise these publication failures and render the actual Home Assistant templates with zero, invalid, stale, future-dated and wrong-unit readings. They do not run Home Assistant itself or prove the behavior of its energy integrator.

The GitHub Actions workflow runs the same checks with read-only repository permissions. A separate job installs pinned ESPHome and checks both synthetic configurations, generated C++, invalid pin rejection and substitution precedence in temporary directories with throwaway credentials. CI does not upload firmware or connect to devices. Use the commands in [the firmware guide](../firmware/README.md) for full compilation. Real board and end-to-end tests are tracked separately in [Verification](verification.md).

## Diagrams

The SVG files in `docs/assets/` are editable source artifacts. Keep text legible at repository display width, use text labels in addition to color, and update the adjacent tables when the design changes. The signal-budget chart counts MCU signal lines only; it is not a bandwidth, latency or performance benchmark.

## Release boundary

This project publishes documentation and configuration templates. A firmware binary is device-specific and must not be presented as ready to flash while pin assignments, flash size, calibration and electrical constraints remain unverified.
