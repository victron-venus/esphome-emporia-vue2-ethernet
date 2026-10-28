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


def yaml_mapping_values(node):
    keys = set()
    for key, value in node.value:
        if not isinstance(key, yaml.ScalarNode):
            raise ValueError('complex YAML mapping key')
        if key.value in keys:
            raise ValueError('duplicate YAML key')
        keys.add(key.value)
        yield value


def yaml_children(node):
    if isinstance(node, yaml.MappingNode):
        return yaml_mapping_values(node)
    if isinstance(node, yaml.SequenceNode):
        return node.value
    return ()


def walk_yaml(node, active, visited):
    if id(node) in active:
        raise ValueError('cyclic YAML alias')
    if id(node) in visited:
        return
    active.add(id(node))
    for child in yaml_children(node):
        walk_yaml(child, active, visited)
    active.remove(id(node))
    visited.add(id(node))


def check_yaml(text):
    # Compose only: !include and !secret stay inert. BaseLoader preserves the
    # Actions key "on" as text instead of YAML 1.1's surprising boolean coercion.
    for document in yaml.compose_all(text, Loader=yaml.BaseLoader):
        if document is not None:
            walk_yaml(document, set(), set())


def svg_root(text):
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
    return root


def register_svg_id(node, ids):
    identifier = node.get('id')
    if not identifier:
        return
    if identifier in ids:
        raise ValueError('duplicate SVG id')
    ids.add(identifier)


def svg_attribute_references(node):
    references = set()
    for name, value in node.attrib.items():
        attribute = name.rsplit('}', 1)[-1].lower()
        if attribute.startswith('on'):
            raise ValueError('SVG event handler')
        if attribute == 'href':
            if not value.startswith('#'):
                raise ValueError('external SVG resource')
            references.add(value[1:])
    return references


def svg_paint_references(node):
    style = ' '.join(node.attrib.values())
    if node.tag == SVG_NS + 'style':
        style += ''.join(node.itertext())
    if '@import' in style.lower():
        raise ValueError('external SVG style')
    references = set()
    for target in re.findall(r'''url\(\s*['"]?([^)'"\s]+)['"]?\s*\)''', style, re.I):
        if not target.startswith('#'):
            raise ValueError('external SVG paint resource')
        references.add(target[1:])
    return references


def check_svg(text):
    root = svg_root(text)
    ids, references = set(), set()
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] in {'script', 'foreignObject'}:
            raise ValueError('executable SVG content')
        register_svg_id(node, ids)
        references.update(svg_attribute_references(node))
        references.update(svg_paint_references(node))
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


def markdown_link_target(token):
    if token.type == 'link_open':
        return token.attrGet('href')
    if token.type == 'image':
        return token.attrGet('src')
    return None


def markdown_targets(text):
    for block in MARKDOWN.parse(text):
        for token in block.children or []:
            target = markdown_link_target(token)
            if target:
                yield target


def local_markdown_target(root, relative, parsed, published):
    unresolved = root / relative
    if parsed.path:
        unresolved = root / relative.parent / unquote(parsed.path)
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
    return local


def check_markdown_fragment(local, fragment):
    if not fragment or local.suffix != '.md':
        return
    if unquote(fragment) not in markdown_anchors(local.read_text(encoding='utf-8')):
        raise ValueError('missing Markdown heading anchor')


def check_markdown_target(root, relative, target, published):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {'', 'https', 'http', 'mailto'}:
            raise ValueError('unsupported link scheme')
        return
    local = local_markdown_target(root, relative, parsed, published)
    check_markdown_fragment(local, parsed.fragment)


def check_markdown(root, relative, text, published):
    for target in markdown_targets(text):
        check_markdown_target(root, relative, target, published)


def published_paths(root, paths):
    return {p for p in paths if (root / p).exists() and not private_artifact(p) and no_symlink(root, p)}


def source_kind(relative):
    kinds = {'.md': 'markdown', '.svg': 'svg', '.yaml': 'yaml', '.yml': 'yaml', '.json': 'json', '.py': 'python'}
    if relative.name.endswith('.json.example'):
        return 'json'
    return kinds.get(relative.suffix)


def check_source_text(root, relative, text, published):
    if re.search(r'[\u0400-\u04ff]', text):
        raise ValueError('documentation and examples must be in English')
    kind = source_kind(relative)
    if kind == 'markdown':
        check_markdown(root, relative, text, published)
    elif kind == 'python':
        ast.parse(text, filename=str(relative))
    elif kind is not None:
        parsers = {'svg': check_svg, 'yaml': check_yaml, 'json': check_json}
        parsers[kind](text)
    return kind


def check_source_file(root, relative, published):
    path = root / relative
    if not no_symlink(root, relative):
        return f'{relative}: symbolic links are not supported', None
    if not path.exists():
        return None, None  # Tracked file removed locally, not a publishable target.
    if not path.is_file() or private_artifact(relative):
        return f'{relative}: private or unsupported source artifact', None
    if path.suffix not in {'.md', '.svg', '.yaml', '.yml', '.json', '.py', '.txt', '.example'}:
        return None, None
    try:
        text = path.read_text(encoding='utf-8')
        kind = check_source_text(root, relative, text, published)
    except (OSError, ValueError, SyntaxError, ET.ParseError, yaml.YAMLError) as exc:
        # Never print excerpts of a mistakenly tracked private configuration.
        return f'{relative}: invalid source ({type(exc).__name__})', None
    return None, kind


def run_checks(root):
    root = root.resolve()
    paths = source_paths(root)
    published = published_paths(root, paths)
    errors, counts = [], {'markdown': 0, 'svg': 0, 'yaml': 0, 'json': 0, 'python': 0}
    for relative in paths:
        error, kind = check_source_file(root, relative, published)
        if error:
            errors.append(error)
        if kind:
            counts[kind] += 1
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
