# Contributing

Keep documentation and examples in English. Explain the problem, proposed change and evidence needed to assess it.

## Hardware reports

A useful report includes the board revision, clear photographs of both sides of a disconnected board, continuity results, exact W5500 module and reset circuit, supply measurements, and the relevant acceptance tests. Distinguish measured facts from candidate connections.

Remove serial numbers, credentials, personal details and unrelated surroundings from photographs and logs. Do not upload flash backups, NVS contents or live configuration files.

## Changes

- Preserve the SAMD09 measurement path unless a change explicitly documents and validates a different design.
- Keep unverified pin assignments out of default packages.
- Do not describe compiler success as proof of hardware behavior or electrical safety.
- Document units, sign convention, unavailable-state handling and energy boundaries for integration examples.
- Keep diagrams as accessible SVG with a title and description; provide equivalent essential information in text or tables.

Run the checks in [Repository maintenance](docs/maintenance.md) before opening a pull request. Include test results and limitations. Never attach a supposedly universal flash image to an unverified wiring proposal.
