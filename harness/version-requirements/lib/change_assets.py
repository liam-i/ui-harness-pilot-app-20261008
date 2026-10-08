"""Fixed Change derivation provenance in the existing Trace; not a delivery Gate.

The output is saved before registration, so its original fixed reference survives
Archive without rewriting the provenance. Current location and use remain the
responsibility of planning/archive/delivery callers.
"""
import re

from .assets import DERIVED, VERSION
from .core import canonical_bytes, parse_json, parse_yaml, relative_path
from .errors import CheckError, InputError
from .models import validate
from .openspec_artifacts import read_observation
from .reviews import evidence
from .sources import fixed_content

TRACE = re.compile(r'requirements/versions/(' + VERSION + r')/trace/changes/(C-[0-9]{3,})\.yaml\Z')


def read_registry(index, reference):
    """Resolve the actual captured Change owner, never infer it from its name."""
    match = TRACE.fullmatch(reference['path'])
    if match is None:
        raise CheckError('asset.change-trace-path', 'Change derivation identity needs its owning candidate Trace')
    trace = validate('planning_trace', parse_yaml(index.store.ref(reference)))
    if (trace['version'], trace['candidate_id']) != match.groups():
        raise CheckError('asset.change-owner', 'fixed Trace path and Version/candidate owner disagree')
    captured = validate('openspec_observation', parse_json(evidence(index.store, trace['observation_ref'])))
    observed = read_observation(index.store, trace['observation_ref'], change=trace['change'],
                                actual_revision=captured['captured_revision'])
    records, paths = {}, set()
    for item in trace.get('asset_derivations', []):
        validate('change_derivation', item)
        name = item['id'] + '@' + str(item['revision'])
        output = item['output_ref']
        relative_path(output['path'])
        prefix = observed['change_root'] + '/assets/' + item['id'] + '/r' + str(item['revision']) + '/'
        if not output['path'].startswith(prefix):
            raise CheckError('asset.change-output-path', 'persistent output belongs to its actual Change and DAS revision directory')
        if name in records or output['path'] in paths:
            raise CheckError('asset.duplicate', 'duplicate Change-derived revision or output path')
        if output['sha256'] != item.get('received_sha256', item['sha256']):
            raise CheckError('asset.change-output-digest', 'saved output reference and derivation received bytes disagree')
        if not index.store.ancestor(output['commit'], captured['captured_revision']):
            raise CheckError('asset.change-output-order', 'save persistent output before its actual planning observation and Trace')
        index.store.ref(output)
        index.store.read(captured['captured_revision'], output['path'], output['sha256'])
        records[name], paths = item, paths | {output['path']}
    return trace, observed, records


def retained_revision(index, reference, trace, name, item):
    """A new capture/Archive may move files; registered output identity stays fixed."""
    store = index.store
    if store.git('rev-parse', '--is-shallow-repository').strip() == b'true':
        raise InputError('git.shallow', 'Change derivation retention needs full reachable history')
    key = ('change-derivation', reference['commit'], reference['path'])
    if key not in index._histories:
        index._histories[key] = store.git('rev-list', '--full-history', reference['commit'],
                                          '--', reference['path']).decode().splitlines()
    for commit in index._histories[key]:
        if reference['path'] not in store.tree(commit):
            continue
        previous = validate('planning_trace', parse_yaml(store.read(commit, reference['path'])))
        if any(previous[k] != trace[k] for k in ('version', 'candidate_id', 'change', 'delivery_line')):
            raise CheckError('asset.change-owner-history', 'registered Change assets cannot be reassigned to another owner')
        rows = [row for row in previous.get('asset_derivations', []) if row['id'] + '@' + str(row['revision']) == name]
        if rows and (len(rows) != 1 or canonical_bytes(rows[0]) != canonical_bytes(item)):
            raise CheckError('asset.revision-overwrite', 'registered Change derivation changed; append a new revision')


def resolve_change_asset(index, value):
    reference = value['manifest_ref']
    trace, observed, records = read_registry(index, reference)
    prefix = trace['change'] + '/'
    identity = value['identity']
    name = identity[len(prefix):] if identity.startswith(prefix) else ''
    if not DERIVED.fullmatch(name):
        raise CheckError('asset.change-identity', 'fixed Change identity must select its actual owner and DAS revision')
    key = (reference['commit'], reference['path'], name)
    if key in index._visiting:
        raise CheckError('asset.cycle', 'derived inputs form a cycle')
    if key in index._resolved:
        return index._resolved[key]
    item = records.get(name)
    if item is None:
        raise CheckError('asset.missing-identity', 'Change derivation is absent from the fixed Trace')
    index._visiting.add(key)
    try:
        retained_revision(index, reference, trace, name, item)
        data, content_ref = fixed_content(index.store, item['output_ref'], item['sha256'], item.get('external'))
        if not data:
            raise CheckError('asset.empty-output', 'persistent Change output is empty')
        index.derivation_inputs(item, owner=index.context,
                                consumer={'identity': identity, 'manifest_ref': reference}, node=key)
        result = {'identity': identity, 'content_ref': content_ref, 'received_ref': item['output_ref'],
                  'manifest_ref': reference, 'node': list(key), 'bytes': data}
        index._resolved[key] = result
        return result
    finally:
        index._visiting.remove(key)


def check_registered_outputs(index, trace, observation, revision, *, registry_ref=None, relocations=None):
    """Inventory actual planning/archived assets without rewriting their owner."""
    store = index.store
    root = observation['change_root'] + '/assets/'
    actual = {path for path in store.tree(revision) if path.startswith(root)}
    records = trace.get('asset_derivations', [])
    if not actual and not records and 'version' not in trace:
        return []
    path = 'requirements/versions/' + trace['version'] + '/trace/changes/' + trace['candidate_id'] + '.yaml'
    names = {row['id'] + '@' + str(row['revision']) for row in records}
    # Removing both a registered row and its file is not cleanup of a draft.
    history = store.git('rev-list', '--full-history', revision, '--', path).decode().splitlines()
    for commit in history:
        if path not in store.tree(commit):
            continue
        previous = validate('planning_trace', parse_yaml(store.read(commit, path)))
        previous_names = {row['id'] + '@' + str(row['revision']) for row in previous.get('asset_derivations', [])}
        if not previous_names <= names:
            raise CheckError('asset.registered-removal', 'retain registered Change revisions; only unregistered previews are disposable')
    if not actual and not records:
        return []
    from .core import digest
    reference = registry_ref or {'commit': revision, 'path': path, 'sha256': digest(store.read(revision, path))}
    if reference['path'] != path:
        raise CheckError('asset.change-registry', 'current derivations must use this candidate Trace reference')
    store.read(revision, path, reference['sha256'])
    saved, _, registered = read_registry(index, reference)
    if saved.get('asset_derivations', []) != records:
        raise CheckError('asset.change-registry', 'current asset inventory must use its actual saved Trace derivations')
    expected, result = set(), []
    relocations = relocations or {}
    for name, item in registered.items():
        value = resolve_change_asset(index, {'identity': trace['change'] + '/' + name, 'manifest_ref': reference})
        original = value['received_ref']
        current = relocations.get(original['path'], original)
        if not current['path'].startswith(root) or current['sha256'] != original['sha256']:
            raise CheckError('asset.change-relocation', 'Archive location must preserve the registered output bytes and actual owner')
        store.ref(current)
        store.read(revision, current['path'], current['sha256'])
        expected.add(current['path'])
        result.append({**{k: v for k, v in value.items() if k != 'bytes'}, 'location_ref': current})
    if actual != expected:
        raise CheckError('asset.inventory', 'Change assets and registered persistent outputs disagree', refs=sorted(actual ^ expected))
    return result
