"""Actual integration history and content, preserving original branch evidence.

These readers establish Git facts and replay the original pre-merge admission.
They do not establish current contribution coverage, G3/integrated, permission
to release a reservation, or semantic equivalence of changed merge results.
"""
import json

from .control_delivery import read_delivery_control
from .core import canonical_bytes, digest, parse_json
from .delivery_trace import current_ref
from .errors import CheckError, InputError
from .final_checks import engineering_paths, unchanged_since
from .models import validate
from .reviews import decision, evidence
from .ui_receipts import compare as compare_ui, historical


def integration_facts(context, *, candidate_id, source, target_before, merged, target,
                      method, declared_inputs=(), control=None, delivery_subject=None):
    """Inspect actual commits; a successful read is not delivery acceptance.

    source is the actual merged feature tip, including retained admission
    evidence. It is distinct from the original tested commit and from merged.
    """
    store = context.store
    for revision in (source, target_before, merged, target):
        store.commit(revision)
    if method not in ('fast-forward', 'merge', 'squash', 'rebase'):
        raise InputError('integration.method-unsupported', 'unsupported integration history method')
    if source == target_before or merged == target_before:
        raise CheckError('integration.no-action', 'an unchanged target is not a new integration')
    if not store.ancestor(target_before, source):
        raise CheckError('integration.source-target', 'the actual source must include its checked target')
    if not store.ancestor(merged, target):
        raise CheckError('integration.wrong-line', 'the claimed integration is absent from the selected target history')
    if not store.ancestor(target_before, merged):
        raise CheckError('integration.target-history', 'integration must continue the actual checked target')
    parents = store.git('show', '-s', '--format=%P', merged).decode().split()
    if method == 'fast-forward':
        valid = merged == source
    elif method == 'merge':
        valid = parents == [target_before, source]
    elif method == 'squash':
        # A one-commit squash can reproduce the same object when all commit
        # metadata also agrees. The original operation identifies the method;
        # a different SHA is not a necessary condition for valid integration.
        valid = parents == [target_before]
    else:
        # A rebased series continues T through single-parent commits. Source
        # ancestry can be absent; content is independently compared below.
        commits = store.git('rev-list', '--first-parent', target_before + '..' + merged).decode().split()
        valid = bool(commits)
        cursor = merged
        for revision in commits:
            chain = store.git('show', '-s', '--format=%P', revision).decode().split()
            valid = valid and revision == cursor and len(chain) == 1
            cursor = chain[0] if len(chain) == 1 else None
        valid = valid and cursor == target_before
    if not valid:
        raise CheckError('integration.method-history', 'declared integration method disagrees with actual Git parents')
    # Keep mode, binary bytes, additions and deletions. A metadata-looking
    # file declared by an original execution is still an engineering input.
    protected = {ref['path'] for ref in declared_inputs}
    for ref in declared_inputs:
        current_ref(store, ref, source)
    def changes(before, after):
        left, right = store.tree(before), store.tree(after)
        paths = (engineering_paths(context, before, candidate_id, control, delivery_subject=delivery_subject) |
                 engineering_paths(context, after, candidate_id, control, delivery_subject=delivery_subject) | protected)
        rows = []
        for path in sorted(paths):
            if left.get(path) == right.get(path):
                continue
            def item(revision, tree):
                if path not in tree:
                    return None
                return {'commit': revision, 'path': path, 'sha256': digest(store.read(revision, path)), 'mode': tree[path][0]}
            rows.append({'path': path, 'before': item(before, left), 'after': item(after, right)})
        return rows
    merged_changes = changes(source, merged)
    target_changes = changes(merged, target)
    return {'source_revision': source, 'target_before_revision': target_before,
            'merged_revision': merged, 'target_revision': target, 'method': method,
            'merge_changes': merged_changes, 'subsequent_changes': target_changes,
            'branch_inputs_preserved': not merged_changes and not target_changes,
            'scope': 'Git history and exact engineering inputs only; changed content needs current evidence and Review; no G3/coverage or slot release'}


def read_integration(context, reference, *, target_revision):
    """Read the original operation and admission, never manufacture a new PASS.

    Caller selects the current target via the usual phase context. Historical
    queries may inspect an older target; neither form authorizes new actions.
    """
    from .premerge import check_pre_merge

    store = context.store
    value = validate('integration_observation', parse_json(evidence(store, reference)))
    prefix = context.vr + '/trace/evidence/'
    if not reference['path'].startswith(prefix):
        raise CheckError('integration.observation-path', 'integration evidence belongs to its existing Version evidence namespace')
    origin_ref = value['pre_merge_context_ref']
    origin = validate('snapshot', parse_json(evidence(store, origin_ref)))
    tiny = origin['subject'].startswith(('task:', 'pr:'))
    if ((origin['gate'], origin['phase'], origin['evaluation_mode']) != ('G3', 'pre-merge', 'current') or
            (origin['version'], origin['delivery_line']) != (context.version['version'], context.version['delivery_line'])):
        raise CheckError('integration.origin', 'integration requires an actual current pre-merge input on this Version/line')
    source = value['source_revision']
    if not store.ancestor(origin['head_revision'], source):
        raise CheckError('integration.source-history', 'source must retain the actual pre-merge head')
    for ref in (origin_ref, value['pre_merge_result_ref']):
        if not store.ancestor(ref['commit'], source):
            raise CheckError('integration.late-admission', 'retain original admission inputs/results before the actual source is merged')
        current_ref(store, ref, source)
    original = parse_json(evidence(store, value['pre_merge_result_ref']))
    fields = ('gate', 'phase', 'subject', 'evaluation_mode', 'version', 'delivery_line',
              'metadata_revision', 'head_revision', 'target_revision', 'control_revision')
    expected = {key: origin[key] for key in fields}
    expected.update(baseline=origin['baseline_ref'], result='passed', exit_code=0)
    if not isinstance(original, dict) or any(original.get(k) != v for k, v in expected.items()):
        raise CheckError('integration.admission-result', 'original pre-merge output differs from its fixed input or did not pass')
    rows = original.get('diagnostics')
    if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or
            rows[0].get('rule_id') != 'G3.pre-merge' or rows[0].get('result') != 'passed' or
            not isinstance(rows[0].get('evidence'), dict) or
            rows[0]['evidence'].get('merge_ready') is not True or
            (not tiny and rows[0]['evidence'].get('alignment_published') is not True)):
        raise CheckError('integration.admission-result', 'an unpublished preview or historical output is not original merge admission')
    with store.input_scope():
        if tiny:
            from .tiny_delivery import check_tiny_pre_merge
            replay = check_tiny_pre_merge(store, historical(origin, getattr(context, 'snapshot', {})))['evidence']
        else:
            replay = check_pre_merge(store, historical(origin, getattr(context, 'snapshot', {})))['evidence']
    # Apply the CLI's JSON boundary before strict canonical validation. The
    # common parser deliberately rejects tuples as stored business records.
    replay = parse_json(json.dumps(replay, ensure_ascii=False, allow_nan=False))
    admitted = rows[0]['evidence']
    compare_ui(context, admitted.get('ui'), replay.get('ui'))
    fields = (('subject', 'tiny_ref', 'baseline_ref', 'delivery', 'final_checks', 'final_review_ref', 'merge_request_ref') if tiny else
              ('change', 'trace_ref', 'baseline_ref', 'reservation_ref', 'alignment_published',
               'pre_archive_context_ref', 'archive', 'delivery', 'final_checks', 'final_review_ref', 'merge_request_ref'))
    for key in fields:
        # CLI output is JSON: internal tuples serialize as arrays. Compare
        # the same JSON meaning, retaining every field and fixed identity.
        if canonical_bytes(admitted.get(key)) != canonical_bytes(replay[key]):
            raise CheckError('integration.admission-replay', 'retained pre-merge output disagrees with recomputed original facts: ' + key, refs=[key])
    control = read_delivery_control(store, origin['control_revision'], ui_context=context.snapshot)
    cid = None if tiny else replay['trace_ref']['path'].rsplit('/', 1)[-1].removesuffix('.yaml')
    subject = origin['subject'] if tiny else None
    unchanged_since(context, origin['head_revision'], source, cid, control=control, delivery_subject=subject)
    confirmation = value['confirmation']
    decision(context, confirmation, roles={'integrator'})
    evidence(store, value['operation_ref'])
    facts = integration_facts(context, candidate_id=cid, source=source, target_before=origin['target_revision'],
        merged=value['merged_revision'], target=target_revision, method=value['method'],
        declared_inputs=replay['final_checks']['input_refs'], control=control, delivery_subject=subject)
    if tiny:
        return {'observation_ref': reference, 'pre_merge_context_ref': origin_ref,
                'pre_merge_result_ref': value['pre_merge_result_ref'], 'subject': subject,
                'tiny_ref': origin['tiny_ref'], 'baseline_ref': origin['baseline_ref'],
                'control_revision': origin['control_revision'], 'original_admission': replay,
                'facts': facts, 'operation_ref': value['operation_ref'], 'confirmation': confirmation,
                'scope': 'original task/PR admission and actual Git integration facts; current delivery needs separate verification'}
    return {'observation_ref': reference, 'pre_merge_context_ref': origin_ref,
            'pre_merge_result_ref': value['pre_merge_result_ref'], 'change': replay['change'],
            'candidate_id': cid, 'baseline_ref': origin['baseline_ref'],
            'reservation_ref': replay['reservation_ref'], 'dispatch_ref': origin['dispatch_ref'],
            'control_revision': origin['control_revision'], 'original_admission': replay,
            'facts': facts, 'operation_ref': value['operation_ref'], 'confirmation': confirmation,
            'scope': 'original admission and actual integration facts only; current BL/control, contribution evidence and Review remain G3/integrated responsibilities'}
