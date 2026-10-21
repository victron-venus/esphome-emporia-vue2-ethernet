# Security

Do not put live credentials, Home Assistant tokens, ESPHome API keys, OTA passwords, flash dumps or NVS contents in issues, examples or commits.

Use encrypted ESPHome API connections and authenticated OTA. Keep the device, Home Assistant and GX bridge on a trusted network with only the required connectivity. Ethernet connectivity alone does not authenticate clients or encrypt application traffic. Use TLS for Home Assistant WebSocket access where supported by the deployment.

If you find a vulnerability, use this repository's **Security → Report a vulnerability** option if available. Otherwise open an issue asking for a private contact method, without exploit details or secrets.

Electrical hazards should be reported with the board revision and disconnected-board evidence. Software security checks do not validate mains isolation or the finished hardware assembly.
