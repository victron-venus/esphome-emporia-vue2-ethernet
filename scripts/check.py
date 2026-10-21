#!/usr/bin/env python3
"""Validate documentation and examples without connecting to any device."""

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", ".esphome", "__pycache__", ".pytest_cache"}
errors = []
counts = {"markdown": 0, "svg": 0, "yaml": 0, "json": 0}

for path in sorted(ROOT.rglob("*")):
    rel = path.relative_to(ROOT)
    if any(part in SKIP for part in rel.parts) or not path.is_file():
        continue
    if path.is_symlink():
        errors.append(f"{rel}: symbolic links are not supported")
        continue
    if path.name in {"secrets.yaml", "secrets.yml", "config.json"} or path.suffix in {".bin", ".elf", ".tfstate", ".tfplan"}:
        errors.append(f"{rel}: local configuration or generated artifact")
        continue
    if path.suffix not in {".md", ".svg", ".yaml", ".yml", ".json", ".py", ".txt", ".example"}:
        continue
    text = path.read_text(encoding="utf-8")
    if re.search(r"[\u0400-\u04ff]", text):
        errors.append(f"{rel}: documentation and examples must be in English")
    try:
        if path.suffix == ".md":
            counts["markdown"] += 1
            for target in re.findall(r"\]\(([^\s)]+)(?:\s+[^)]*)?\)", text):
                target = target.strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                local = (path.parent / unquote(parsed.path)).resolve()
                if not local.is_relative_to(ROOT) or not local.exists():
                    errors.append(f"{rel}: missing or out-of-tree link {target}")
        elif path.suffix == ".svg":
            counts["svg"] += 1
            svg = ET.fromstring(text)
            ns = "{http://www.w3.org/2000/svg}"
            if svg.tag != ns + "svg" or not svg.get("viewBox"):
                errors.append(f"{rel}: SVG root and viewBox required")
            if svg.find(ns + "title") is None or svg.find(ns + "desc") is None:
                errors.append(f"{rel}: accessible title and description required")
            if any(node.tag in {ns + "script", ns + "foreignObject"} for node in svg.iter()):
                errors.append(f"{rel}: executable SVG content is not allowed")
        elif path.suffix in {".yaml", ".yml"}:
            counts["yaml"] += 1
            list(yaml.compose_all(text, Loader=yaml.SafeLoader))
        elif path.suffix == ".json" or path.name.endswith(".json.example"):
            counts["json"] += 1
            json.loads(text)
    except (ValueError, ET.ParseError, yaml.YAMLError) as exc:
        errors.append(f"{rel}: invalid document ({type(exc).__name__})")

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("Documentation and example checks passed: " + json.dumps(counts, sort_keys=True))
print("No firmware upload, live connection or hardware verification was performed.")
