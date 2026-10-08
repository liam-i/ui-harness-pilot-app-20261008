"""S6 facts for existing/external delivery, using the original scope/map/plan/E.

No candidate, Change, Tasks, Archive, synthetic merge, reservation or second
Trace is created. Passing a selected scope does not complete a Version.
"""
from collections import defaultdict

from .context import resolve
from .control_delivery import read_delivery_control
from .core import canonical_bytes
from .delivery import DeliveryIndex
from .delivery_trace import coverage_identity, current_ref
from .dispatch import baseline_context, current_engineering, preserved_inputs, retain_inputs
from .errors import CheckError
from .feasibility import check_feasibility
from .requirements import RequirementIndex
from .review_scope import References, ReviewScope
from .reviews import check_review
from .verification import check_execution
from .worktree import capture


def selected_scope(delivery, subject):
    parts = subject.removeprefix('scope:').split('/')
    requirements = delivery.requirements
    selected = set()
    for uid, info in requirements.records.items():
        if len(parts) > 1 and parts[1] != uid:
            continue
        for ac in info['acs']:
            if len(parts) == 3 and parts[2] != ac:
                continue
            # One R may allocate existing ACs and unfinished candidate ACs.
            # Select the actual complete contribution set of this AC; the
            # Requirement's overall delivery mode must not hide either path.
            if any(delivery.allocations[ref]['node'] not in delivery.endpoints
                   for ref in delivery.coverage[(uid, ac)]):
                raise CheckError('scope-delivery.path', 'selected scope requires its actual candidate delivery; do not bypass a Change', refs=[uid, ac])
            selected.add((uid, ac))
    if not selected:
        raise CheckError('scope-delivery.empty', 'selected scope contains no included acceptance obligation')
    return selected


def scope_executions(delivery, selected, verification_inputs, target):
    """Bind reviewed plan obligations to current executions and endpoint contracts.

    The plan's existing evidence_refs select E; E already owns case/AC/code/test
    associations. Human scope-delivery review remains responsible for meaning,
    verification level/method and environment suitability.
    """
    store, context = delivery.store, delivery.context
    obligations = [row for row in delivery.plan['obligations']
                   if 'requirement' in row and
                   any((row['requirement'], ac) in selected for ac in row['acceptance']) and
                   (row['checkpoint'] in ('contribution', 'integration') or row['evidence_refs'])]
    due = {canonical_bytes(ref): ref for row in obligations for ref in row['evidence_refs']}
    expected = {canonical_bytes(row['verification_ref']): row for row in verification_inputs}
    if len(expected) != len(verification_inputs) or expected.keys() != due.keys() or not due:
        raise CheckError('scope-delivery.executions', 'execution expectations must exactly select actual E from every due reviewed obligation')
    executions = {}
    for key, ref in due.items():
        row = expected[key]
        if row['tested_revision'] != target:
            raise CheckError('scope-delivery.stale-target', 'scope evidence must test the actual selected target')
        checked = check_execution(context, ref, tested_revision=target, identities=row['identities'], engineering_review=delivery.review)
        for coverage in checked['record']['coverage']:
            coverage_identity(delivery, coverage)
        for item in [*checked['record']['input_refs'], *checked['record']['identities'].values()]:
            current_ref(store, item, target)
        executions[key] = checked
    accepted, verified, links = defaultdict(set), defaultdict(set), []
    engineering = delivery.review['engineering']
    contracts = {canonical_bytes(ref) for ref in engineering['spec_refs'] + engineering['shared_contract_refs']}
    for obligation in obligations:
        pairs = {(obligation['requirement'], ac) for ac in obligation['acceptance']} & selected
        supplied = defaultdict(set)
        if not obligation['evidence_refs']:
            raise CheckError('scope-delivery.obligation', 'due obligation has no actual verification evidence', refs=[obligation['id']])
        for reference in obligation['evidence_refs']:
            checked = executions[canonical_bytes(reference)]
            inputs = checked['record']['input_refs']
            for coverage in checked['record']['coverage']:
                contribution = coverage['contribution']
                if contribution not in obligation['contributions'] or 'requirement' not in coverage:
                    continue
                matched = {(coverage['requirement'], ac) for ac in coverage['acceptance']} & pairs
                if not matched:
                    continue
                allocation = delivery.allocations[contribution]
                endpoint = delivery.endpoints[allocation['node']]
                contract = endpoint['contract_ref']
                if endpoint['target_line_path'] == 'port-planned':
                    raise CheckError('scope-delivery.pending-port', 'a planned port is not an actual target-line delivery')
                if reference not in endpoint['availability_refs']:
                    raise CheckError('scope-delivery.endpoint-evidence', 'selected E is not the reviewed provider availability evidence')
                current_ref(store, contract, target)
                if canonical_bytes(contract) not in contracts or contract not in inputs:
                    raise CheckError('scope-delivery.contract', 'provider contract must be reviewed and included in its actual execution')
                if endpoint['kind'] == 'existing':
                    if contract not in engineering['spec_refs'] or not contract['path'].startswith('openspec/specs/'):
                        raise CheckError('scope-delivery.main-spec', 'existing capability needs its reviewed current main Spec')
                    if engineering['code_ref'] not in inputs:
                        raise CheckError('scope-delivery.implementation', 'existing capability evidence must include the reviewed actual implementation')
                for pair in matched:
                    supplied[pair].add(contribution)
                links.append({'obligation_id': obligation['id'], 'contribution': contribution,
                              'verification_ref': reference, 'case_ids': coverage['case_ids']})
        for pair in pairs:
            required = set(obligation['contributions']) & delivery.coverage[pair]
            if not required <= supplied[pair]:
                raise CheckError('scope-delivery.coverage', 'actual cases do not cover all contributions of the due obligation', refs=[obligation['id'], *pair])
            accepted[pair].update(supplied[pair])
            verified[pair].add(obligation['id'])
    for pair in selected:
        if accepted[pair] != delivery.coverage[pair]:
            raise CheckError('scope-delivery.coverage', 'selected AC lacks actual current provider coverage', refs=list(pair))
    return {'acceptance': [{'requirement': uid, 'acceptance': ac,
                           'contributions': sorted(accepted[(uid, ac)]), 'obligations': sorted(verified[(uid, ac)])}
                          for uid, ac in sorted(selected)],
            'verification_links': links,
            'deferred_obligations': [row['id'] for row in delivery.plan['obligations']
                                    if 'requirement' in row and row['checkpoint'] in ('completion', 'release') and
                                    any((row['requirement'], ac) in selected for ac in row['acceptance'])]}


def check_scope_delivery(store, snapshot):
    context = resolve(store, snapshot)
    required = ('engineering_inputs', 'verification_inputs')
    if not snapshot['control_revision'] or any(key not in snapshot for key in required):
        raise CheckError('scope-delivery.context', 'scope delivery needs current engineering inputs, actual E expectations and control')
    head, target = snapshot['head_revision'], snapshot['target_revision']
    if not store.ancestor(target, head):
        raise CheckError('scope-delivery.target-history', 'delivery metadata must descend from the actual target')
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    baseline, checked = baseline_context(store, snapshot)
    inputs = snapshot['engineering_inputs']
    if inputs['engineering_review_ref']['path'] != context.vr + '/reviews/engineering.yaml':
        raise CheckError('scope-delivery.review-owner', 'use the existing Version engineering Review')
    current = current_engineering(baseline, snapshot, inputs)
    for revision in {snapshot['metadata_revision'], head, target, current.content_commit}:
        preserved_inputs(baseline, revision, checked)
    requirements = RequirementIndex(baseline)
    requirements.check_content()
    delivery = DeliveryIndex(requirements, engineering_context=current, map_ref=inputs['map_ref'],
                             verification_plan_ref=inputs['verification_plan_ref'])
    if delivery.map['baseline'] != baseline.baseline['id']:
        raise CheckError('scope-delivery.baseline', 'engineering map must retain the selected effective baseline')
    delivery.check()
    check_feasibility(delivery)
    scope = ReviewScope(requirements, delivery)
    engineering = scope.check_engineering()
    scope.engineering_questions.check_baseline(requirements.records)
    selected = selected_scope(delivery, snapshot['subject'])
    from .ui_integration import check as check_ui, execution_inputs, CHECKS
    contributions = {ref for pair in selected for ref in delivery.coverage[pair]}
    ui = check_ui(delivery, snapshot, kind='scope', subject=snapshot['subject'],
                  contributions=contributions, action='scope-accept')
    # Scope/AC semantics are reviewed against the same bound map, plan and E.
    # This adds a delivery check to the existing review, not a parallel status.
    check_review(current, 'reviews/engineering.yaml', 'engineering', (),
                 roles={'engineering-owner'}, required_checks=('scope-delivery',) + (CHECKS if ui else ()))
    verified = scope_executions(delivery, selected, snapshot['verification_inputs'], target)
    ui = execution_inputs(delivery, ui, snapshot['verification_inputs'])
    # A broad query expands into the existing control identities; it does not
    # add a second namespace of broad scope targets to the published history.
    subjects = {'version:' + snapshot['version']}
    for uid, ac in selected:
        subjects.update({'requirement:' + snapshot['version'] + '/' + uid,
                         'scope:' + snapshot['version'] + '/' + uid + '/' + ac})
    holds = [row for entry in ('propose', 'apply', 'merge', 'release')
             for row in control.holds.blockers(line=snapshot['delivery_line'], entry=entry, subjects=subjects)]
    references = References(current)
    for value in (snapshot, engineering, verified):
        references.fixed(value)
    pins = retain_inputs(baseline, [snapshot[key] for key in ('metadata_revision', 'head_revision', 'target_revision')])
    if snapshot['evaluation_mode'] == 'current':
        live = capture(store, extra_roots=['openspec'])
        if live.record['base_revision'] != head or live.record['changes']:
            raise CheckError('scope-delivery.uncommitted-inputs', 'current delivery needs its actual clean metadata head')
        live.assert_current(store)
    resolve(store, snapshot)
    return {'rule_id': 'G3.integrated', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'baseline_ref': snapshot['baseline_ref'], 'engineering_inputs': inputs,
                         'target_revision': target, 'delivery': verified, 'current_holds': holds,
                         'ui': ui,
                         'retained_pins': pins,
                         'scope': 'selected existing/external delivery facts only; no Change, capacity, action authorization or Version Completion'},
            'next_owner': 'engineering-owner'}
