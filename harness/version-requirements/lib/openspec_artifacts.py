"""Read captured OpenSpec observations against fixed Git artifacts.

The existing CLI supplies paths and schema status. This module executes neither
repo scripts nor model workflows. Captures must come from the controlled existing
toolchain; authentic capture and semantic Review are separate responsibilities.
"""
from pathlib import PurePosixPath
import re

import yaml
from markdown_it import MarkdownIt

from .core import MAX_DOCUMENT_BYTES, UniqueLoader, canonical_bytes, digest, json_value, parse_json, parse_yaml, relative_path
from .errors import CheckError, InputError
from .models import unique, validate
from .reviews import evidence


class MetadataLoader(UniqueLoader):
    """Accept native generated dates without changing Requirement YAML policy."""


MetadataLoader.add_constructor('tag:yaml.org,2002:timestamp', lambda loader, node: loader.construct_scalar(node))
MetadataLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in rules if tag != 'tag:yaml.org,2002:bool']
    for key, rules in UniqueLoader.yaml_implicit_resolvers.items()}
MetadataLoader.add_implicit_resolver('tag:yaml.org,2002:bool', re.compile(r'^(?:true|True|TRUE|false|False|FALSE)$'), list('tTfF'))


def metadata_yaml(data):
    try:
        if len(data) > MAX_DOCUMENT_BYTES:
            raise ValueError('OpenSpec metadata exceeds 16 MiB')
        value = yaml.load(data.decode('utf-8-sig'), Loader=MetadataLoader)
        json_value(value)
        return value
    except (UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError) as error:
        raise InputError('openspec.metadata-yaml', str(error)) from error


def absolute(value):
    if not isinstance(value, str):
        raise InputError('openspec.path', 'an observed absolute POSIX path is required')
    path = PurePosixPath(value)
    if not path.is_absolute() or str(path) != value or '..' in path.parts or '\\' in value:
        raise InputError('openspec.path', 'noncanonical observed path', refs=[value])
    return path


def relative(value, root):
    path = absolute(value)
    if not path.is_relative_to(root):
        raise InputError('openspec.outside-project', 'external planning stores need an explicitly supported object store; never guess a repo path', refs=[value])
    result = str(path.relative_to(root))
    relative_path(result)
    return result


def task_evidence(data, *, store=None):
    """Read optional reference-only Task notes without interpreting them as proof.

    The reserved terminal fence can hold only existing Task IDs and fixed file
    references. Other Markdown remains planning content. Evidence meaning,
    completeness, execution status and authorization belong to their owners.
    """
    try:
        if len(data) > MAX_DOCUMENT_BYTES:
            raise ValueError('Task content exceeds the document limit')
        content = data.decode('utf-8')
    except (UnicodeError, ValueError) as error:
        raise InputError('openspec.tasks-encoding', str(error)) from error
    found = [t for t in MarkdownIt().parse(content)
             if t.type == 'fence' and t.level == 0 and t.info == 'harness-task-evidence']
    if not found:
        return data, []
    if len(found) != 1:
        raise CheckError('openspec.task-evidence-format', 'use one terminal reference-only evidence fence')
    token = found[0]
    lines = content.splitlines(keepends=True)
    start, end = token.map
    if (end != len(lines) or lines[start] != '```harness-task-evidence\n' or
            lines[end - 1] not in ('```', '```\n') or start == 0):
        raise CheckError('openspec.task-evidence-format', 'append the exact terminal evidence fence after a separator newline')
    prefix = ''.join(lines[:start])
    if not prefix.endswith('\n'):
        raise CheckError('openspec.task-evidence-format', 'missing evidence separator')
    # The writer appends one separator newline; remove exactly that byte. The
    # approved prefix keeps its original whitespace and end-of-file convention.
    planning = prefix[:-1].encode()
    document = validate('task_evidence_links', parse_json(token.content.encode()))
    entries = document['entries']
    unique(entries, 'task_id', location='Task evidence')
    if store is not None:
        for row in entries:
            for reference in row['refs']:
                store.ref(reference)
    return planning, entries


def tasks(data):
    """Match the qualified CLI's checkbox scope, then retain displayed X.Y IDs.

    The CLI lists ordinal task IDs; those are not stable Trace identities. Lines
    inside fences count in the qualified CLI too, so none are silently omitted.
    """
    planning, notes = task_evidence(data)
    content = planning.decode('utf-8')
    result, lines = {}, []
    for line in content.split('\n'):
        match = re.match(r'^\s*[-*]\s*\[([\sxX])\]\s*(.*)', line)
        if match:
            description = match[2].strip()
            identity = re.match(r'([0-9]+\.[0-9]+)\s+\S', description)
            if not identity or identity[1] in result:
                raise CheckError('openspec.task-identity', 'tasks require unique displayed X.Y IDs and nonempty descriptions')
            result[identity[1]] = {'description': description, 'done': match[1].lower() == 'x'}
            # State and the reference-only footer do not change planning.
            line = line[:match.start(1)] + ' ' + line[match.end(1):]
        lines.append(line)
    if not result:
        raise CheckError('openspec.tasks-empty', 'no actual tracked tasks')
    if any(row['task_id'] not in result for row in notes):
        raise CheckError('openspec.task-evidence-task', 'evidence refers to an absent displayed Task ID')
    return result, '\n'.join(lines).encode()


def _object(value, keys, location):
    if not isinstance(value, dict) or not set(keys) <= value.keys():
        raise InputError('openspec.output-shape', 'missing CLI output fields', refs=[location, list(keys)])
    return value


def _rows(value, location):
    if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
        raise InputError('openspec.output-shape', 'expected a list of objects', refs=[location])
    return value


def _identified(value, location):
    rows = _rows(value, location)
    if any(not isinstance(v.get('id'), str) or not v['id'] for v in rows):
        raise InputError('openspec.output-shape', 'expected named entries', refs=[location])
    return unique(rows, 'id', location=location)


def _paths(value, root, location):
    if not isinstance(value, list):
        raise InputError('openspec.output-shape', 'expected a path list', refs=[location])
    return [relative(v, root) for v in value]


def read_observation(store, reference, *, change, actual_revision, allow_task_progress=False):
    """Check captured planning inputs; no Gate, dependency or Apply permission."""
    value = validate('openspec_observation', parse_json(evidence(store, reference)))
    if value['change'] != change or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', change):
        raise CheckError('openspec.change', 'observation and selected logical Change differ')
    captured = store.commit(value['captured_revision'])
    store.commit(actual_revision)
    root = absolute(value['project_root'])
    expected_args = {'schema': ['schema', 'which', 'spec-driven', '--json'],
                     'status': ['status', '--change', change, '--json'],
                     'apply': ['instructions', 'apply', '--change', change, '--json'],
                     'validate': ['validate', change, '--strict', '--json']}
    outputs = {}
    for name, command in value['commands'].items():
        if command['args'] != expected_args[name] or command['exit_code'] != 0:
            raise CheckError('openspec.command', 'captured required query failed or used different arguments', refs=[name])
        ref = {**command['stdout_ref'], 'commit': command['stdout_ref'].get('commit', reference['commit'])}
        outputs[name] = parse_json(evidence(store, ref))
    schema_origin = _object(outputs['schema'], ('name', 'source', 'path'), 'schema')
    if schema_origin['name'] != 'spec-driven' or schema_origin['source'] != 'package':
        raise InputError('openspec.schema-source', 'this integration requires the qualified built-in spec-driven Schema')
    schema = parse_yaml(evidence(store, value['schema_ref']))
    _object(schema, ('name', 'artifacts', 'apply'), 'schema content')
    # A different artifact model is not silently treated as the current Lite policy.
    definitions = _identified(schema['artifacts'], 'OpenSpec schema')
    _object(schema['apply'], ('requires', 'tracks'), 'Schema apply')
    patterns = {'proposal': 'proposal.md', 'specs': 'specs/**/*.md', 'design': 'design.md', 'tasks': 'tasks.md'}
    dependencies = {'proposal': [], 'specs': ['proposal'], 'design': ['proposal'], 'tasks': ['specs', 'design']}
    if (schema['name'] != 'spec-driven' or set(definitions) != set(patterns) or
            any(definitions[k].get('generates') != p or definitions[k].get('requires') != dependencies[k] for k, p in patterns.items()) or
            schema['apply'].get('requires') != ['tasks'] or schema['apply'].get('tracks') != 'tasks.md'):
        raise InputError('openspec.schema-contract', 'Schema artifact contract differs from the qualified integration')
    status = _object(outputs['status'], ('changeName', 'schemaName', 'planningHome', 'changeRoot', 'artifactPaths', 'artifacts', 'applyRequires'), 'status')
    apply = _object(outputs['apply'], ('changeName', 'schemaName', 'changeDir', 'contextFiles', 'progress', 'tasks', 'state'), 'instructions apply')
    home = _object(status['planningHome'], ('kind', 'root', 'changesDir'), 'planningHome')
    if home['kind'] != 'repo' or absolute(home['root']) != root:
        raise InputError('openspec.planning-store', 'this fixed Git reader supports repo-local planning only; preserve the actual external locator')
    changes = relative(home['changesDir'], root)
    change_root = relative(status['changeRoot'], root)
    if change_root != changes + '/' + change or relative(apply['changeDir'], root) != change_root:
        raise CheckError('openspec.locator', 'status and Apply context locate different Changes')
    if any(o['changeName'] != change or o['schemaName'] != schema['name'] for o in (status, apply)):
        raise CheckError('openspec.change', 'CLI outputs disagree on Change or Schema')
    for name in ('status', 'apply', 'validate'):
        query_root = _object(outputs[name], ('root',), name)['root']
        if not isinstance(query_root, dict) or absolute(query_root.get('path')) != root:
            raise CheckError('openspec.query-root', 'queries were not run against one planning project')
    inputs = unique(value['input_refs'], 'path', location='OpenSpec captured inputs')
    for ref in inputs.values():
        if ref['commit'] != captured:
            raise CheckError('openspec.capture-input', 'all observed project inputs must bind the captured revision')
        store.ref(ref)
    prefix = change_root + '/'
    tree = store.tree(captured)
    current = store.tree(actual_revision)
    old_files = {p for p in tree if p.startswith(prefix)}
    new_files = {p for p in current if p.startswith(prefix)}
    if old_files != new_files or not old_files <= inputs.keys():
        raise CheckError('openspec.artifact-set', 'Change files were added/removed or omitted from the observation', refs=sorted(old_files ^ new_files | (old_files - inputs.keys())))
    # Binding the actual wrapper/config stops using queries captured before a
    # project switched source, schema or delivery policy. No execution here.
    required = {'openspec/config.yaml', 'scripts/openspec.sh', 'scripts/adapt-openspec-workflows.mjs', 'harness/openspec-profile.json'}
    if 'harness/openspec-version' in tree:
        required.add('harness/openspec-version')
    else:
        required.update(('package.json', 'package-lock.json'))
    if not required <= inputs.keys():
        raise CheckError('openspec.tool-input', 'capture omits project CLI/configuration inputs', refs=sorted(required - inputs.keys()))
    schema_prefix = 'openspec/schemas/'
    old_overrides, new_overrides = ({p for p in t if p.startswith(schema_prefix)} for t in (tree, current))
    if old_overrides != new_overrides or not old_overrides <= inputs.keys():
        raise CheckError('openspec.schema-override', 'Schema overrides changed or were omitted after package-source observation')
    artifact_paths = _object(status['artifactPaths'], patterns, 'artifactPaths')
    states = _identified(status['artifacts'], 'OpenSpec status')
    if set(artifact_paths) != set(patterns) or set(states) != set(patterns) or status['applyRequires'] != schema['apply']['requires']:
        raise InputError('openspec.status-contract', 'status differs from its Schema artifact set')
    resolved = {}
    for name, pattern in patterns.items():
        row = _object(artifact_paths[name], ('outputPath', 'resolvedOutputPath', 'existingOutputPaths'), name)
        if row['outputPath'] != pattern or relative(row['resolvedOutputPath'], root) != prefix + pattern:
            raise CheckError('openspec.artifact-path', 'CLI output pattern differs from its Schema', refs=[name])
        listed = _paths(row['existingOutputPaths'], root, name)
        actual = {p for p in old_files if re.fullmatch(re.escape(prefix) + r'specs/(?:.*/)?[^/]+\.md', p)} if name == 'specs' else ({prefix + pattern} & old_files)
        if len(listed) != len(set(listed)) or set(listed) != actual:
            raise CheckError('openspec.artifact-set', 'CLI Artifact list differs from the complete fixed Git inputs', refs=[name])
        if any(not store.read(captured, p).strip() for p in listed):
            raise CheckError('openspec.empty-artifact', 'empty file is not a planning Artifact', refs=[name])
        resolved[name] = sorted(listed)
    metadata_path = prefix + '.openspec.yaml'
    metadata = metadata_yaml(store.read(captured, metadata_path))
    _object(metadata, ('schema',), 'Change metadata')
    if metadata.get('schema') != schema['name'] or 'skip_design' in metadata:
        raise CheckError('openspec.metadata', 'wrong Schema or invented skip_design marker')
    skip = metadata.get('skip_specs', False)
    if not isinstance(skip, bool) or (skip and resolved['specs']) or (not skip and not resolved['specs']):
        raise CheckError('openspec.specs', 'actual Delta files and skip_specs disagree')
    for name, row in states.items():
        expected = 'skipped' if name == 'specs' and skip else 'done' if resolved[name] else 'ready'
        if row.get('status') != expected or row.get('outputPath') != patterns[name] or row.get('requires') != dependencies[name]:
            raise CheckError('openspec.artifact-status', 'CLI state differs from actual Artifact content', refs=[name])
    if not resolved['proposal'] or not resolved['tasks']:
        raise CheckError('openspec.planning-incomplete', 'actual Proposal and tracked Tasks are required')
    expected_context = {k: v for k, v in resolved.items() if v}
    _object(apply['contextFiles'], (), 'Apply contextFiles')
    observed_context = {k: sorted(_paths(paths, root, k)) for k, paths in apply['contextFiles'].items()}
    if observed_context != expected_context:
        raise CheckError('openspec.apply-context', 'Apply context omits or adds an Artifact')
    task_path = resolved['tasks'][0]
    parsed, normalized = tasks(store.read(captured, task_path))
    current_tasks, _ = tasks(store.read(actual_revision, task_path))
    task_evidence(store.read(captured, task_path), store=store)
    _, notes = task_evidence(store.read(actual_revision, task_path), store=store)
    progress = {'total': len(parsed), 'complete': sum(t['done'] for t in parsed.values()), 'remaining': sum(not t['done'] for t in parsed.values())}
    listed_tasks = [{'id': str(i), **t} for i, t in enumerate(parsed.values(), 1)]
    if apply['tasks'] != listed_tasks or apply['progress'] != progress or apply['state'] != ('all_done' if progress['remaining'] == 0 else 'ready'):
        raise CheckError('openspec.task-observation', 'Apply query does not match actual task lines')
    validation = _object(outputs['validate'], ('items',), 'validate')
    items = _rows(validation['items'], 'validate items')
    if (len(items) != 1 or items[0].get('id') != change or
            items[0].get('type') != 'change' or items[0].get('valid') is not True or
            any(issue.get('level') == 'ERROR' for issue in _rows(items[0].get('issues', []), 'validate issues'))):
        raise CheckError('openspec.strict-validation', 'strict validation did not pass for the selected Change')
    planning_refs = []
    for p, ref in inputs.items():
        before = store.ref(ref)
        after = store.read(actual_revision, p)
        if p == task_path:
            _, normalized_after = tasks(after)
            same = normalized == normalized_after if allow_task_progress else before == after
            semantic = normalized
        else:
            same, semantic = before == after, before
        if not same:
            raise CheckError('openspec.stale-observation', 'planning or configuration changed after the captured CLI queries', refs=[p])
        planning_refs.append({'path': p, 'sha256': digest(semantic)})
    return {'change': change, 'captured_revision': captured, 'change_root': change_root,
            'planning_home': home, 'artifacts': resolved, 'tasks': current_tasks, 'task_evidence': notes,
            'tasks_revision': actual_revision, 'skip_specs': skip,
            'design_present': bool(resolved['design']), 'input_refs': list(inputs.values()),
            'planning_digest': digest(canonical_bytes(sorted(planning_refs, key=lambda r: r['path']))),
            'observation_ref': reference, 'scope': 'captured CLI and fixed Artifact consistency only; semantic Review and Gate permission remain separate'}
