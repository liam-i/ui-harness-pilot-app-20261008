"""Read an actual isolated Archive commit and preserve historical file identities.

The existing Skill or CLI still performs Archive/Sync. This reader checks the
fixed observation, complete move and links; final Review/CI/control belong to G3.
"""
from copy import deepcopy
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit

from .core import digest, parse_json, parse_yaml
from .errors import CheckError, InputError
from .markdown_source import parse_document, parser, resolve_link
from .models import validate
from .openspec_artifacts import absolute, read_observation, relative, task_evidence, tasks
from .reviews import evidence


def markdown_identity(store, revision, path, *, moves=None, section=None):
    """Compare parsed content, resolving links independently at each location.

    Only parser positions/source spellings are discarded. Text, code, token
    structure, attributes and all reference definitions remain in the identity.
    The original bytes remain fixed evidence; this is not a planning digest.
    """
    raw = store.read(revision, path)
    parsed = parse_document(raw)
    if parsed['unsupported'] or parsed['duplicate_references']:
        raise InputError('archive.markdown-unsupported', 'link preservation requires unambiguous supported Markdown; retain and review unsupported content', refs=[path])
    files, documents, refs = store.tree(revision), {}, []
    def target(value):
        try:
            url = urlsplit(value)
        except ValueError as error:
            raise InputError('archive.link', 'invalid Markdown target', refs=[path, value]) from error
        if url.scheme or url.netloc or value.startswith(('/', '\\')):
            return {'external': value}
        located = resolve_link(path, value, files, documents)
        linked = located['path']
        if located['anchor'] and linked in files and linked.endswith('.md'):
            documents.setdefault(linked, parse_document(store.read(revision, linked)))
            located = resolve_link(path, value, files, documents)
        if located['status'] != 'resolved':
            raise CheckError('archive.link', 'Markdown link is not resolvable at its actual location', refs=[path, value, located])
        content = store.read(revision, linked)
        reference = {'commit': revision, 'path': linked, 'sha256': digest(content)}
        if reference not in refs:
            refs.append(reference)
        return {'path': (moves or {}).get(linked, linked), 'anchor': located['anchor']}
    env = {}
    tokens = parser().parse(raw.decode('utf-8-sig'), env)
    definitions = env.get('references', {})
    if section is not None:
        # Parse the full document first: a retained Requirement can use a
        # reference definition outside its own section. Slicing raw Markdown
        # first would silently turn such links into ordinary text.
        start, end = section
        first = next(i for i, t in enumerate(tokens) if t.map and t.map[0] == start - 1)
        last = next((i for i in range(first + 1, len(tokens))
                     if tokens[i].map and tokens[i].map[0] >= end), len(tokens))
        tokens = tokens[first:last]
        def labels(token):
            values = {token.meta['label']} if token.meta.get('label') else set()
            for child in token.children or []:
                values.update(labels(child))
            return values
        used = set().union(*(labels(t) for t in tokens))
        definitions = {label: row for label, row in definitions.items()
                       if label in used or start - 1 <= row['map'][0] < end}
    def token_identity(token):
        value = token.as_dict()
        for key in ('map', 'level', 'meta'):
            value.pop(key, None)
        if token.type == 'inline':
            value['content'] = ''  # Actual text/formatting remains in children.
        attrs = dict(token.attrs)
        for key in ('href', 'src'):
            if key in attrs:
                attrs[key] = target(attrs[key])
        value['attrs'] = attrs
        value['children'] = [token_identity(t) for t in token.children or []]
        return value
    identity = [token_identity(t) for t in tokens]
    definitions = {label: {'href': target(row['href']), 'title': row['title']}
                   for label, row in definitions.items()}
    return {'tokens': identity, 'definitions': definitions}, refs


def synced_spec_ref(delivery, spec, observed, archived, head_revision, *, control=None):
    """Derive a current main-Spec locator without rewriting planning history.

    Only a file changed by this verified Sync is eligible. The selected complete
    Requirement (including its Scenario, links and reference definitions) must
    survive both Sync and subsequent integration. Final Review still binds the
    whole current main Spec and judges the semantics of the actual Sync.
    """
    from .delivery_trace import current_ref
    from .planning_trace import spec_target

    store, reference = delivery.store, spec['file_ref']
    path, before = reference['path'], archived['before_revision']
    if (not path.startswith('openspec/specs/') or not path.endswith('/spec.md') or
            path not in archived['changed_main_specs']):
        current_ref(store, reference, head_revision)
        return reference
    current_ref(store, reference, before)
    selected = spec_target(store, spec, observed, before)
    original, linked = markdown_identity(store, before, path, section=selected['requirement_lines'])
    mode = store.tree(before)[path][:2]
    for revision in (archived['archive_revision'], head_revision):
        current = {'commit': revision, 'path': path, 'sha256': digest(store.read(revision, path))}
        if store.tree(revision)[path][:2] != mode:
            raise CheckError('archive-trace.spec-mode', 'the referenced main Spec changed file mode', refs=[reference, current])
        located = spec_target(store, {**spec, 'file_ref': current}, observed, revision)
        actual, _ = markdown_identity(store, revision, path, section=located['requirement_lines'])
        if actual != original:
            raise CheckError('archive-trace.spec-content', 'Sync or later integration changed the historically linked main Requirement', refs=[spec, current])
        for ref in linked:
            # Self navigation resolves against the same selected main document;
            # its old whole-file digest is precisely what this projection must
            # not mistake for an unchanged-Requirement contract. Other linked
            # inputs retain the existing asset/metadata preservation checks.
            if ref['path'] != path:
                preserved_link(store, ref, revision, delivery=delivery, control=control)
    return current


def preserved_link(store, reference, revision, *, delivery=None, control=None):
    """Keep historical bytes; only known, separately checked metadata may advance.

    A Markdown navigation link does not freeze an append-only control source or
    replace the current engineering Review. This grants no publication authority
    and never exempts source/derived assets or explicit execution inputs.
    """
    from .control import check_source_append, event
    from .delivery_trace import current_ref
    from .models import unique

    path = reference['path']
    original = store.ref(reference)
    current = store.read(revision, path)
    if store.tree(reference['commit'])[path][:2] != store.tree(revision)[path][:2]:
        raise CheckError('delivery-trace.file-mode', 'linked input changed file mode', refs=[reference])
    if original == current:
        return original
    if delivery is not None:
        context = delivery.context
        if context.store is not store:
            raise CheckError('archive.link-context', 'linked metadata must use the same delivery store')
        selected = {context.vr + '/delivery-map.yaml': delivery.map_ref,
                    context.vr + '/verification-plan.yaml': delivery.verification_plan_ref}
        review_path = context.vr + '/reviews/engineering.yaml'
        if path == review_path:
            selected[path] = {'commit': context.content_commit, 'path': path,
                              'sha256': digest(store.read(context.content_commit, path))}
        if path in selected and selected[path]['path'] == path:
            current_ref(store, selected[path], revision)
            return original
        if control is not None:
            published = control.record_refs.get(path)
            if published is not None and control.event_refs.get(published['event_id']) == published:
                owner = event(store, published)
                if (owner['version'], owner['target_line']) == (context.version['version'], context.version['delivery_line']):
                    actual = {'commit': revision, 'path': path, 'sha256': digest(current)}
                    for raw in (original, current):
                        document = validate('events', parse_yaml(raw), location=path)
                        unique(document['events'], 'event_id', location=path)
                    check_source_append(store, reference, actual)
                    check_source_append(store, published, actual)
                    return original
    # Unclassified links remain fixed, including arbitrary files in requirements.
    return current_ref(store, reference, revision)


def read_archive(store, reference, *, change, actual_revision, delivery=None, control=None):
    """No action, final CI, semantic Sync verdict or merge permission."""
    value = validate('openspec_archive_observation', parse_json(evidence(store, reference)))
    if value['change'] != change:
        raise CheckError('archive.change', 'archive observation belongs to a different logical Change')
    before, archived = value['before_revision'], value['archive_revision']
    for revision in (before, archived, actual_revision):
        store.commit(revision)
    parents = store.git('rev-list', '--parents', '-n', '1', archived).decode().strip().split()[1:]
    if parents != [before] or not store.ancestor(archived, actual_revision):
        raise CheckError('archive.history', 'Archive must be a separate single-parent commit in this head history')
    observed = read_observation(store, value['planning_observation_ref'], change=change,
                                actual_revision=before, allow_task_progress=True)
    if not observed['tasks'] or not all(row['done'] for row in observed['tasks'].values()):
        raise CheckError('archive.tasks-incomplete', 'actual pre-archive Tasks are incomplete; CLI --yes is not acceptance')
    root = absolute(value['project_root'])
    if str(root) != observed['planning_home']['root']:
        raise CheckError('archive.project', 'Archive and planning observations belong to different projects')
    active = observed['change_root']
    archive_root = str(PurePosixPath(active).parent) + '/archive/'
    skip_sync = False
    if 'command' in value:
        command = value['command']
        normal = ['archive', change, '--yes', '--json']
        skipped = [*normal, '--skip-specs']
        if command['exit_code'] != 0 or command['args'] not in (normal, skipped):
            raise CheckError('archive.command', 'Archive failed or used unsupported arguments; validation cannot be skipped')
        output_ref = {**command['stdout_ref'], 'commit': command['stdout_ref'].get('commit', reference['commit'])}
        output = parse_json(evidence(store, output_ref))
        result = output.get('archive') if isinstance(output, dict) else None
        if (not isinstance(result, dict) or result.get('change') != change or
                not isinstance(output.get('root'), dict) or output['root'].get('path') != str(root) or
                not isinstance(result.get('specsUpdated'), bool)):
            raise CheckError('archive.output', 'captured Archive result does not identify a successful operation in this project')
        location = relative(result.get('path'), root)
        name = result.get('archivedAs')
        skip_sync = command['args'] == skipped or not result['specsUpdated']
        operation_refs = [output_ref]
        method = 'cli'
    else:
        workflow = value['workflow']
        receipt = validate('archive_move_receipt', parse_json(evidence(store, workflow['execution_ref'])))
        if (receipt['project_root'], receipt['change'], receipt['before_revision']) != (str(root), change, before):
            raise CheckError('archive.move-binding', 'original move process belongs to different inputs or Change')
        if receipt['exit_code'] != 0:
            raise CheckError('archive.command', 'the actual move process did not succeed')
        source, destination = receipt['source'], receipt['destination']
        if source != str(root / active) or receipt['command'] not in (['mv', source, destination], ['mv', '--', source, destination]):
            raise CheckError('archive.move-command', 'original move must name the actual source and destination without extra operands')
        location = relative(destination, root)
        name = PurePosixPath(location).name
        skip_sync = workflow['sync'] != 'synced'
        # This is original process/workflow evidence, not a claim that a model
        # followed every instruction or that Sync was semantically correct.
        operation_refs = [workflow[key] for key in ('execution_ref', 'workflow_ref', 'sync_evidence_ref')]
        operation_refs.extend(receipt[key] for key in ('stdout_ref', 'stderr_ref'))
        for item in operation_refs:
            store.ref(item)
        instruction = workflow['workflow_ref']
        store.read(before, instruction['path'], instruction['sha256'])
        method = 'workflow'
    if not isinstance(name, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}-' + re.escape(change), name) or location != archive_root + name:
        raise CheckError('archive.locator', 'actual archive locator is not the captured dated logical Change')
    old, new, head = (store.tree(r) for r in (before, archived, actual_revision))
    old_files = {p for p in old if p.startswith(active + '/')}
    moves = {p: location + p[len(active):] for p in old_files}
    if any(p.startswith(location + '/') for p in old) or any(p.startswith(active + '/') for p in new) or any(p.startswith(active + '/') for p in head):
        raise CheckError('archive.move', 'Archive destination was not new, or the active Change still exists/has been restored')
    expected = set(moves.values())
    if {p for p in new if p.startswith(location + '/')} != expected or {p for p in head if p.startswith(location + '/')} != expected:
        raise CheckError('archive.file-set', 'Archive must preserve every file, including metadata, Tasks, attachments and unknown extras')
    refs, links = [], []
    task_path = observed['artifacts']['tasks'][0]
    for source, destination in sorted(moves.items()):
        prior, saved = store.read(before, source), store.read(archived, destination)
        if old[source][:2] != new[destination][:2] or new[destination] != head[destination]:
            raise CheckError('archive.file-mode', 'Archive file mode or current archived content differs from the saved move', refs=[source, destination])
        if source.endswith('.md'):
            left, _ = markdown_identity(store, before, source, moves=moves)
            right, moved_links = markdown_identity(store, archived, destination)
            if left != right:
                raise CheckError('archive.content', 'Archive changed parsed Markdown beyond relocating its existing links', refs=[source, destination])
            # Keep source/asset bytes fixed. Known current engineering metadata
            # and append-only control navigation are checked in their own roles.
            _, current_links = markdown_identity(store, actual_revision, destination)
            if [r['path'] for r in moved_links] != [r['path'] for r in current_links]:
                raise CheckError('archive.link-content', 'a current archived link no longer selects the fixed saved bytes', refs=[destination])
            for linked in moved_links:
                try:
                    preserved_link(store, linked, actual_revision, delivery=delivery, control=control)
                except CheckError as error:
                    if error.rule != 'ref.digest':
                        raise
                    raise CheckError('archive.link-content', 'a current archived link no longer selects the fixed saved bytes', refs=[destination]) from error
            links.extend(moved_links)
        elif prior != saved:
            raise CheckError('archive.content', 'Archive changed an attachment or non-Markdown file', refs=[source, destination])
        if source == task_path:
            original_tasks, _ = tasks(prior)
            saved_tasks, _ = tasks(saved)
            task_evidence(saved, store=store)
            if {key: row['done'] for key, row in original_tasks.items()} != {key: row['done'] for key, row in saved_tasks.items()}:
                raise CheckError('archive.task-identity', 'Archive changed Task identity or completion state')
        refs.append({'before_ref': {'commit': before, 'path': source, 'sha256': digest(prior)},
                     'archived_ref': {'commit': archived, 'path': destination, 'sha256': digest(saved)}})
    main_paths = {str(PurePosixPath(p.replace(active + '/specs/', 'openspec/specs/', 1)))
                  for p in observed['artifacts']['specs']}
    changed = {p for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
    if changed - old_files - expected - main_paths:
        raise CheckError('archive.commit-scope', 'Archive commit includes code, evidence metadata, unrelated specs or other work', refs=sorted(changed - old_files - expected - main_paths))
    changed_main = sorted(changed & main_paths)
    if (observed['skip_specs'] or skip_sync) and changed_main:
        raise CheckError('archive.sync-mode', 'claimed no-Sync Archive also changed main Specs')
    main_refs, main_links = [], []
    for path in sorted(main_paths & new.keys()):
        # Sync may copy a requirement's relative links into a shallower main
        # Spec. A successful CLI operation does not prove these still resolve.
        _, saved_links = markdown_identity(store, archived, path)
        _, current_links = markdown_identity(store, actual_revision, path)
        for linked in [*saved_links, *current_links]:
            changes = str(PurePosixPath(active).parent) + '/'
            if linked['path'].startswith(changes) and not linked['path'].startswith(archive_root):
                raise CheckError('archive.main-active-link', 'long-lived main Spec depends on an active Change path', refs=[path, linked])
        main_refs.append({'archived_ref': {'commit': archived, 'path': path, 'sha256': digest(store.read(archived, path))},
                          'current_ref': {'commit': actual_revision, 'path': path, 'sha256': digest(store.read(actual_revision, path))}})
        main_links.extend(current_links)
    return {'change': change, 'before_revision': before, 'archive_revision': archived,
            'active_path': None, 'archived_path': location, 'file_moves': refs,
            'changed_main_specs': changed_main, 'linked_refs': links,
            'method': method, 'operation_refs': operation_refs,
            'main_spec_refs': main_refs, 'main_linked_refs': main_links,
            'observation_ref': reference, 'planning_observation_ref': value['planning_observation_ref'],
            'scope': 'actual Archive commit/file/link preservation only; no semantic Sync approval, G3, final CI, merge or slot release'}


def check_archived_delivery(delivery, reference, *, head_revision, verification_inputs, control=None):
    """Locate the same Trace after Archive and check actual post-Archive E.

    The original planning refs remain authoritative history. Only the verified
    file move derives current locators; no synthetic CLI capture is written.
    The caller still owes admission, final Review/CI/control and action checks.
    """
    from .delivery_trace import check_delivery_trace, current_ref

    store, context = delivery.store, delivery.context
    trace = validate('planning_trace', parse_yaml(current_ref(store, reference, head_revision)))
    path = context.vr + '/trace/changes/' + trace['candidate_id'] + '.yaml'
    if reference['path'] != path:
        raise CheckError('archive-trace.path', 'archived delivery must continue its original candidate Trace path')
    archive_ref = trace.get('delivery', {}).get('archive_observation_ref')
    if archive_ref is None:
        raise CheckError('archive-trace.required', 'archived delivery requires the actual retained Archive observation')
    if trace['delivery'].get('integration_observation_ref') is not None:
        raise CheckError('archive-trace.integration-required', 'integrated delivery must use its actual integration phase')
    archived = read_archive(store, archive_ref, change=trace['change'], actual_revision=head_revision,
                            delivery=delivery, control=control)
    projected_info = archived_projection(delivery, trace, archived, head_revision=head_revision,
                                         trace_ref=reference, control=control)
    projected, view = projected_info['trace'], projected_info['observation']
    assets, asset_refs = projected_info['assets'], projected_info['asset_refs']
    validate('delivery_verification_inputs', verification_inputs)
    for item in verification_inputs:
        if not store.ancestor(archived['archive_revision'], item['tested_revision']):
            raise CheckError('archive-trace.execution-phase', 'final delivery execution must test the actual Archive commit or its descendant; preserve earlier E as history')
    verified = check_delivery_trace(delivery, projected, view, head_revision=head_revision,
                                    verification_inputs=verification_inputs, control=control)
    return {'trace_ref': reference, 'pre_archive_trace_ref': projected_info['pre_archive_trace_ref'], 'archive': archived,
            'delivery': verified, 'assets': assets, 'asset_refs': asset_refs,
            'observation': view,
            'scope': 'archived Trace/file/asset-use and post-Archive execution associations only; no final CI/Review, G3, merge or slot release'}


def archived_projection(delivery, trace, archived, *, head_revision, trace_ref=None, control=None):
    """Project already verified Archive facts at the actual delivery target.

    No ancestry waiver: the integrated caller proves the original source
    Archive and actual target integration separately before supplying facts.
    """
    from .delivery_trace import current_ref
    from .planning_applicability import stable_trace
    from .planning_trace import check_asset_uses, check_links

    store, context = delivery.store, delivery.context
    path = context.vr + '/trace/changes/' + trace['candidate_id'] + '.yaml'
    expected = {row['archived_ref']['path'] for row in archived['file_moves']}
    tree = store.tree(head_revision)
    if {p for p in tree if p.startswith(archived['archived_path'] + '/')} != expected:
        raise CheckError('archive.file-set', 'integrated Archive must retain its complete original file set')
    for row in archived['file_moves']:
        current_ref(store, row['archived_ref'], head_revision)
        if row['archived_ref']['path'].endswith('.md'):
            markdown_identity(store, head_revision, row['archived_ref']['path'])
    for ref in archived['linked_refs']:
        preserved_link(store, ref, head_revision, delivery=delivery, control=control)
    before = archived['before_revision']
    original_ref = {'commit': before, 'path': path, 'sha256': digest(store.read(before, path))}
    original = validate('planning_trace', parse_yaml(store.ref(original_ref)))
    if stable_trace(original) != stable_trace(trace):
        raise CheckError('archive-trace.planning', 'Archive cannot silently replace AC, Spec, Task or asset planning associations')
    if (original.get('delivery') is None or original['delivery'].get('archive_observation_ref') is not None or
            original['delivery']['task_ref'] != trace['delivery']['task_ref']):
        raise CheckError('archive-trace.origin', 'keep the actual pre-archive Task reference; current locators derive from the verified move')
    observed = read_observation(store, trace['observation_ref'], change=trace['change'],
                                actual_revision=before, allow_task_progress=True)
    if any(p.startswith(observed['change_root'] + '/') for p in tree):
        raise CheckError('archive.move', 'the integrated Change cannot also be active')
    if trace['planning_digest'] != observed['planning_digest']:
        raise CheckError('archive-trace.digest', 'Trace does not select the actual pre-archive planning inputs')
    check_links(delivery, original, observed, before)
    check_asset_uses(delivery, original, observed, before, registry_ref=original_ref)
    moves = {row['before_ref']['path']: row for row in archived['file_moves']}
    task_path = observed['artifacts']['tasks'][0]

    def relocate(ref, *, progress=False):
        row = moves.get(ref['path'])
        if row is None:
            current_ref(store, ref, head_revision)
            return ref
        old, expected = store.ref(ref), store.ref(row['before_ref'])
        equal = tasks(old)[1] == tasks(expected)[1] if progress else old == expected
        if not equal or store.tree(ref['commit'])[ref['path']][:2] != store.tree(before)[ref['path']][:2]:
            raise CheckError('archive-trace.reference', 'historical Artifact ref does not select the actual file before Archive', refs=[ref])
        return row['archived_ref']

    projected = deepcopy(trace)
    projected['delivery'].pop('archive_observation_ref')
    projected['delivery'].pop('integration_observation_ref', None)
    for link in projected['links']:
        for spec in link['specs']:
            spec['file_ref'] = (relocate(spec['file_ref']) if spec['file_ref']['path'] in moves else
                                synced_spec_ref(delivery, spec, observed, archived, head_revision, control=control))
    for use in projected['asset_uses']:
        use['used_in'] = [relocate(ref, progress=ref['path'] == task_path) for ref in use['used_in']]
    if tasks(store.ref(trace['delivery']['task_ref']))[0] != observed['tasks']:
        raise CheckError('archive-trace.task-state', 'historical delivery Tasks differ from their actual completion state before Archive')
    projected['delivery']['task_ref'] = relocate(trace['delivery']['task_ref'], progress=True)
    view = deepcopy(observed)
    view['artifacts'] = {kind: [moves[p]['archived_ref']['path'] for p in paths]
                         for kind, paths in observed['artifacts'].items()}
    view['change_root'] = archived['archived_path']
    raw = store.ref(projected['delivery']['task_ref'])
    view['tasks'], _ = tasks(raw)
    _, view['task_evidence'] = task_evidence(raw, store=store)
    view['tasks_revision'] = head_revision
    view['input_refs'] = [relocate(ref, progress=ref['path'] == task_path) for ref in observed['input_refs']]
    view['scope'] = 'derived archive locators from fixed original CLI observation and verified Git move; not a new CLI query'
    asset_locations = {path: row['archived_ref'] for path, row in moves.items()
                       if path.startswith(observed['change_root'] + '/assets/')}
    assets, asset_refs = check_asset_uses(delivery, projected, view, head_revision,
                                        registry_ref=trace_ref, relocations=asset_locations)
    return {'trace': projected, 'observation': view, 'assets': assets, 'asset_refs': asset_refs,
            'pre_archive_trace_ref': original_ref}
