#!/usr/bin/env python3
"""Validate publishable source without reading ignored secrets or build trees."""
import ast
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from markdown_it import MarkdownIt
import yaml

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = MarkdownIt('commonmark')
SVG_NS = '{http://www.w3.org/2000/svg}'


def source_paths(root):
    result = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root, capture_output=True, check=True,
    )
    return sorted({Path(name) for name in result.stdout.decode().split('\0') if name})


def private_artifact(path):
    name = path.name.lower()
    return (
        any(part in {'.esphome', '.terraform', '.venv', 'backups', '__pycache__'} for part in path.parts)
        or name in {'secrets.yaml', 'secrets.yml', 'config.json', '.env'}
        or name.startswith('.env.') or '.tfstate' in name
        or name.endswith(('.bin', '.elf', '.map', '.log', '.tfplan', '.tfvars', '.tfvars.json', '.local.yaml', '.local.yml', '.local.json'))
    )


def no_symlink(root, relative):
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return False
    return True


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('non-finite JSON number')
    return number


def reject_constant(_value):
    raise ValueError('non-standard JSON constant')


def check_json(text):
    json.loads(text, object_pairs_hook=unique_object, parse_float=finite_float, parse_constant=reject_constant)


def check_yaml(text):
    # Compose only: !include and !secret stay inert. BaseLoader preserves the
    # Actions key "on" as text instead of YAML 1.1's surprising boolean coercion.
    def walk(node, active, visited):
        if id(node) in active:
            raise ValueError('cyclic YAML alias')
        if id(node) in visited:
            return
        active.add(id(node))
        if isinstance(node, yaml.MappingNode):
            keys = set()
            for key, value in node.value:
                if not isinstance(key, yaml.ScalarNode):
                    raise ValueError('complex YAML mapping key')
                if key.value in keys:
                    raise ValueError('duplicate YAML key')
                keys.add(key.value)
                walk(value, active, visited)
        elif isinstance(node, yaml.SequenceNode):
            for value in node.value:
                walk(value, active, visited)
        active.remove(id(node))
        visited.add(id(node))
    for document in yaml.compose_all(text, Loader=yaml.BaseLoader):
        if document is not None:
            walk(document, set(), set())


def check_svg(text):
    if re.search(r'<!DOCTYPE|<!ENTITY|<\?xml-stylesheet', text, re.I):
        raise ValueError('SVG document declarations are not supported')
    root = ET.fromstring(text)
    if root.tag != SVG_NS + 'svg':
        raise ValueError('SVG root required')
    box = [float(n) for n in root.get('viewBox', '').replace(',', ' ').split()]
    if len(box) != 4 or not all(math.isfinite(n) for n in box) or min(box[2:]) <= 0:
        raise ValueError('valid SVG viewBox required')
    for tag in ('title', 'desc'):
        element = root.find(SVG_NS + tag)
        if element is None or not ''.join(element.itertext()).strip():
            raise ValueError('SVG accessibility text required')
    ids, references = set(), set()
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] in {'script', 'foreignObject'}:
            raise ValueError('executable SVG content')
        if node.get('id'):
            if node.get('id') in ids:
                raise ValueError('duplicate SVG id')
            ids.add(node.get('id'))
        for name, value in node.attrib.items():
            attribute = name.rsplit('}', 1)[-1].lower()
            if attribute.startswith('on'):
                raise ValueError('SVG event handler')
            if attribute == 'href':
                if not value.startswith('#'):
                    raise ValueError('external SVG resource')
                references.add(value[1:])
        style = ' '.join(node.attrib.values())
        if node.tag == SVG_NS + 'style':
            style += ''.join(node.itertext())
        if '@import' in style.lower():
            raise ValueError('external SVG style')
        for target in re.findall(r'''url\(\s*['"]?([^)'"\s]+)['"]?\s*\)''', style, re.I):
            if not target.startswith('#'):
                raise ValueError('external SVG paint resource')
            references.add(target[1:])
    if references - ids:
        raise ValueError('missing SVG reference')


def markdown_anchors(text):
    """Heading IDs for the plain GitHub-style headings used in this project."""
    result, counts = set(), {}
    tokens = MARKDOWN.parse(text)
    for index, token in enumerate(tokens):
        if token.type != 'heading_open':
            continue
        children = tokens[index + 1].children or []
        title = ''.join(child.content for child in children if child.type in {'text', 'code_inline'})
        slug = re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-')
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(slug if count == 0 else f'{slug}-{count}')
    return result


def check_markdown(root, relative, text, published):
    for block in MARKDOWN.parse(text):
        for token in block.children or []:
            target = token.attrGet('href') if token.type == 'link_open' else token.attrGet('src') if token.type == 'image' else None
            if not target:
                continue
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                if parsed.scheme not in {'', 'https', 'http', 'mailto'}:
                    raise ValueError('unsupported link scheme')
                continue
            unresolved = root / relative.parent / unquote(parsed.path) if parsed.path else root / relative
            local = unresolved.resolve()
            if not local.is_relative_to(root):
                raise ValueError('link leaves repository')
            if not no_symlink(root, unresolved.relative_to(root)):
                raise ValueError('symbolic link target')
            destination = local.relative_to(root)
            if destination not in published and not any(destination in item.parents for item in published):
                raise ValueError('link target is not publishable source')
            if not local.exists():
                raise ValueError('missing link target')
            if parsed.fragment and local.suffix == '.md':
                if unquote(parsed.fragment) not in markdown_anchors(local.read_text(encoding='utf-8')):
                    raise ValueError('missing Markdown heading anchor')


def run_checks(root):
    root = root.resolve()
    paths = source_paths(root)
    published = {p for p in paths if (root / p).exists() and not private_artifact(p) and no_symlink(root, p)}
    errors, counts = [], {'markdown': 0, 'svg': 0, 'yaml': 0, 'json': 0, 'python': 0}
    for relative in paths:
        path = root / relative
        if not no_symlink(root, relative):
            errors.append(f'{relative}: symbolic links are not supported')
            continue
        if not path.exists():
            continue  # Tracked file removed locally, not a publishable target.
        if not path.is_file() or private_artifact(relative):
            errors.append(f'{relative}: private or unsupported source artifact')
            continue
        suffix = path.suffix
        if suffix not in {'.md', '.svg', '.yaml', '.yml', '.json', '.py', '.txt', '.example'}:
            continue
        try:
            text = path.read_text(encoding='utf-8')
            if re.search(r'[\u0400-\u04ff]', text):
                raise ValueError('documentation and examples must be in English')
            if suffix == '.md':
                check_markdown(root, relative, text, published)
                counts['markdown'] += 1
            elif suffix == '.svg':
                check_svg(text)
                counts['svg'] += 1
            elif suffix in {'.yaml', '.yml'}:
                check_yaml(text)
                counts['yaml'] += 1
            elif suffix == '.json' or path.name.endswith('.json.example'):
                check_json(text)
                counts['json'] += 1
            elif suffix == '.py':
                ast.parse(text, filename=str(relative))
                counts['python'] += 1
        except (OSError, ValueError, SyntaxError, ET.ParseError, yaml.YAMLError) as exc:
            # Never print excerpts of a mistakenly tracked private configuration.
            errors.append(f'{relative}: invalid source ({type(exc).__name__})')
    return errors, counts


def main():
    try:
        errors, counts = run_checks(ROOT)
    except subprocess.CalledProcessError:
        print('Run source checks from a Git checkout.', file=sys.stderr)
        return 1
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Documentation and example checks passed: ' + json.dumps(counts, sort_keys=True))
    print('No firmware upload, live connection or hardware verification was performed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
