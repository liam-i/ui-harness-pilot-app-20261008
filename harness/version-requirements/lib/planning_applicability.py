"""Revalidate an original planning approval without replacing its evidence.

The current engineering Review owns the impact conclusion. This reader checks
its scope and actual target changes; it cannot infer semantic non-impact.
"""
from copy import deepcopy
from dataclasses import replace

from .context import phase_identity
from .control import event
from .control_delivery import KINDS, read_delivery_control
from .core import canonical_bytes, digest, parse_json, parse_yaml
from .delivery import DeliveryIndex
from .errors import CheckError
from .models import unique, validate
from .reviews import evidence


def target_changes(store, before, after):
    """Complete engineering diff, including additions and deletions.

    Version records have their own current BL/Q/map checks. Tooling, code,
    shared specs, tests, config and assets outside that domain all remain here.
    """
    old, new = store.tree(before), store.tree(after)
    rows = []
    for path in sorted(old.keys() | new.keys()):
        if path.startswith('requirements/') or old.get(path) == new.get(path):
            continue
        def ref(revision, tree):
            return {'commit': revision, 'path': path, 'sha256': digest(store.read(revision, path))} if path in tree else None
        rows.append({'path': path, 'before_ref': ref(before, old), 'after_ref': ref(after, new)})
    return rows


def assessment_scope(delivery):
    rows = unique(delivery.review['engineering'].get('planning_applicability', []),
                  'candidate_id', location='planning applicability')
    for cid, row in rows.items():
        if cid not in delivery.candidates or row['target_revision'] != delivery.review['engineering']['code_ref']['commit']:
            raise CheckError('planning.assessment-scope', 'planning assessment must belong to this map and reviewed engineering target', refs=[cid])
        for key in ('origin_snapshot_ref', 'origin_review_ref', 'observation_ref', 'evidence_ref'):
            evidence(delivery.store, row[key])
    return rows


def stable_trace(trace):
    """Comparison of the actual planning associations, not the event envelope.

    A new capture may locate the same Spec bytes in a later commit. Source/DAS
    owner identities stay exact; no general removal of commit identities.
    """
    value = deepcopy(trace)
    for key in ('dispatch_ref', 'observation_ref'):
        value.pop(key)
    # Actual delivery references do not change the approved planning scope.
    # Their correctness belongs to delivery checks and its separate Review.
    value.pop('delivery', None)
    # deepcopy preserves YAML aliases. Rebuild only the locator branches so a
    # shared ref never loses an authoritative commit in design/source/owner.
    def locator(reference):
        return {key: item for key, item in reference.items() if key != 'commit'}
    value['links'] = [{**row, 'specs': [{**spec, 'file_ref': locator(spec['file_ref'])}
                                     for spec in row['specs']]} for row in value['links']]
    value['asset_uses'] = [{**row, 'used_in': [locator(ref) for ref in row['used_in']]}
                           for row in value['asset_uses']]
    return value


def requirement_contract(delivery, cid):
    """The candidate's business and related constraints, at the selected BL.

    Include incoming constraints as well as outgoing relations: a new system
    obligation may constrain an otherwise byte-identical leaf Requirement.
    Unrelated requirements do not force a new whole-plan approval.
    """
    index = delivery.requirements
    selected = {row['requirement'] for row in delivery.candidates[cid]['allocation']}
    related = {}
    for uid, info in index.records.items():
        value = info['value']
        targets = [value['hierarchy']['parent']]
        targets += [row.get('target', row.get('requirement')) for row in value['constraints'] + value['relationships']
                    if row.get('type') != 'related-to' and row.get('strength') != 'informational']
        related[uid] = [target for target in targets if target is not None]
    changed = True
    while changed:
        old = set(selected)
        for uid, targets in related.items():
            names = {target for target in targets if isinstance(target, str)}
            if uid in selected or names & selected:
                selected.add(uid)
                selected.update(names)
        changed = selected != old
    facts = {}
    for uid in sorted(selected):
        info = index.target(uid)
        facts[uid] = {'value': info['value'], 'configuration': info['configuration_ref']['sha256']}
        for target in related.get(uid, []):
            if isinstance(target, dict):
                historical = index.target(target)
                facts[canonical_bytes(target).decode()] = {
                    'value': historical['value'], 'configuration': historical['configuration_ref']['sha256']}
    return {'requirements': facts, 'candidate': delivery.candidates[cid]}


def retain_approval(delivery, snapshot, current, control):
    """Return the validated original Review iff current no-impact is proven.

    Original snapshot/Trace/Review are read and checked, not a historical PASS
    string. Full current engineering Review and G2 checks belong to the caller.
    """
    from .dispatch import same_engineering
    from .planning_trace import check_planning_trace

    store, cid = delivery.store, current['trace']['candidate_id']
    row = assessment_scope(delivery).get(cid)
    if row is None:
        raise CheckError('planning.assessment-required', 'a retained approval needs a current input applicability assessment')
    if row['conclusion'] != 'no-impact':
        raise CheckError('planning.reassessment-required', 'current assessment requires Update, repartition or Requirement clarification before using the old plan', refs=[row['conclusion']])
    if row['target_revision'] != snapshot['target_revision'] or row['observation_ref'] != current['trace']['observation_ref']:
        raise CheckError('planning.assessment-binding', 'assessment does not bind the actual current target and planning observation')
    origin = validate('snapshot', parse_json(evidence(store, row['origin_snapshot_ref'])))
    phase_identity(origin)
    if ((origin['gate'], origin['phase'], origin['subject'], origin['version'], origin['delivery_line']) !=
            ('G2', 'planning', snapshot['subject'], snapshot['version'], snapshot['delivery_line'])):
        raise CheckError('planning.origin-scope', 'original approval belongs to a different candidate, baseline or planning phase')
    if origin['control_revision'] is None or not store.ancestor(origin['control_revision'], snapshot['control_revision']):
        raise CheckError('planning.origin-control', 'original planning must name an actual predecessor of the current control history')
    original_control = read_delivery_control(store, origin['control_revision'], ui_context=snapshot)
    original_reservation = original_control.reservations.get((snapshot['delivery_line'], snapshot['version'], cid))
    if original_reservation is None or original_reservation['event_ref'] != origin['dispatch_ref']:
        raise CheckError('planning.origin-control', 'reservation/alignment was not the confirmed current event in the original planning snapshot')
    old_event = event(store, origin['dispatch_ref'])
    if control.event_refs.get(origin['dispatch_ref']['event_id']) != origin['dispatch_ref'] or old_event['kind'] not in KINDS:
        raise CheckError('planning.origin-publication', 'original planning must refer to an actual published reservation/alignment')
    old_payload = validate(KINDS[old_event['kind']], old_event['payload'])
    if (old_payload['candidate_id'] != cid or old_payload['baseline_ref'] != origin['baseline_ref'] or
            old_payload['target_revision'] != origin['target_revision']):
        raise CheckError('planning.origin-scope', 'original planning snapshot and published inputs disagree')
    from .ui_receipts import historical
    old_snapshot = historical(origin, snapshot)
    old_context = replace(delivery.context.at(old_payload['engineering_review_ref']['commit'], snapshot['version']), snapshot=old_snapshot)
    old_requirements = delivery.requirements
    cross_baseline = origin['baseline_ref'] != snapshot['baseline_ref']
    if cross_baseline:
        from .dispatch import baseline_context
        from .requirements import RequirementIndex
        control.changes.baseline_chain(origin['baseline_ref'], snapshot['baseline_ref'],
                                       version=snapshot['version'], line=snapshot['delivery_line'])
        old_baseline, _ = baseline_context(store, old_snapshot)
        old_requirements = RequirementIndex(old_baseline)
        old_requirements.check_content()
    old_delivery = DeliveryIndex(old_requirements, engineering_context=old_context,
                                map_ref=old_payload['map_ref'], verification_plan_ref=old_payload['verification_plan_ref'])
    old_delivery.check()
    from .ui_integration import candidate as check_ui, candidate_contract
    original_ui = check_ui(old_delivery, old_snapshot, cid, action='propose')
    if (original_ui['contract'] if original_ui else None) != candidate_contract(delivery, snapshot, cid):
        raise CheckError('ui.planning-reassessment', 'UI package, coverage, difference, applicability or policy changed; retain work and use the original Update/review path')
    old = check_planning_trace(old_delivery, origin['trace_ref'], old_snapshot, old_payload,
                               allow_task_progress=origin.get('apply_origin_ref') is not None)
    ref = row['origin_review_ref']
    expected_path = delivery.context.vr + '/reviews/planning/' + cid + '.yaml'
    if ref['path'] != expected_path or store.ref(ref) != store.read(origin['metadata_revision'], expected_path):
        raise CheckError('planning.origin-review', 'fixed original Review differs from the one actually checked')
    for revision in {snapshot['metadata_revision'], snapshot['head_revision']}:
        store.read(revision, expected_path, ref['sha256'])
    allowed = {p for paths in old['observation']['artifacts'].values() for p in paths}
    allowed.add(old['observation']['change_root'] + '/.openspec.yaml')
    allowed.update(ref['path'] for ref in old['observation']['input_refs']
                   if ref['path'].startswith(old['observation']['change_root'] + '/assets/'))
    if origin.get('apply_origin_ref') is not None:
        from .planning import check_planning
        with store.input_scope():
            check_planning(store, old_snapshot)
    else:
        same_engineering(store, origin['target_revision'], origin['head_revision'], planning_files=allowed)
    expected = target_changes(store, origin['target_revision'], snapshot['target_revision'])
    if canonical_bytes(sorted(row['target_changes'], key=lambda v: v['path'])) != canonical_bytes(expected):
        raise CheckError('planning.target-diff', 'impact review omits, adds or misidentifies actual engineering changes', refs=expected)
    old_trace, current_trace = stable_trace(old['trace']), stable_trace(current['trace'])
    if cross_baseline:
        if requirement_contract(old_delivery, cid) != requirement_contract(delivery, cid):
            raise CheckError('planning.requirement-changed', 'candidate obligations or related constraints changed; Update and a new whole-plan Review are required')
        # Only this qualified RC chain and unchanged contract permits changing
        # the contextual BL reference. stable_trace itself retains that field.
        old_trace['baseline_ref'] = current_trace['baseline_ref']
    if old_trace != current_trace:
        raise CheckError('planning.approval-stale', 'planning content or AC/Spec/Task/asset associations changed; use actual Update and a new planning Review')
    old_schema = parse_json(store.ref(old['trace']['observation_ref']))['schema_ref']
    new_schema = parse_json(store.ref(current['trace']['observation_ref']))['schema_ref']
    if store.ref(old_schema) != store.ref(new_schema):
        raise CheckError('planning.approval-stale', 'actual Schema content changed after the original planning approval')
    return {'review': old['review'], 'review_ref': ref, 'origin_snapshot_ref': row['origin_snapshot_ref'],
            'execution_inputs': old['execution_inputs'],
            'assessment': row, 'target_changes': expected}
