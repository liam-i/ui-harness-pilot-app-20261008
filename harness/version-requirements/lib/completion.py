"""G4 reads the complete Version, its actual candidate and retained evidence.

The candidate fixes product/build identity. Later plan evidence, named reviews
and decisions remain separate immutable inputs; saving them does not retest
their own Git commit. Nothing here writes status, approves or deploys a product.
"""
from collections import defaultdict
from dataclasses import replace
import re

from .availability import assessment_scope, provider_contract, provider_evidence
from .context import resolve
from .control_delivery import read_delivery_control
from .core import canonical_bytes, digest, parse_json, parse_yaml
from .delivery import DeliveryIndex
from .delivery_trace import coverage_identity, current_ref
from .dispatch import baseline_context, current_engineering, preserved_inputs, retain_inputs
from .errors import CheckError
from .feasibility import check_feasibility
from .integrated_receipt import read_integrated_receipt
from .models import unique, validate
from .requirements import RequirementIndex
from .review_scope import References, ReviewScope
from .reviews import check_review, decision, evidence
from .verification import _time, check_execution
from .worktree import capture

COMPLETION_CHECKS = ('version-scope', 'combination-acceptance', 'traceability',
                     'build-provenance', 'evidence-applicability', 'issues-and-changes')
RELEASE_CHECKS = ('release-conditions', 'deployment-target', 'release-authorization')


def retained_record(context, reference, kind, prefix):
    value = validate(kind, parse_yaml(evidence(context.store, reference)))
    identity = value['id']
    if (not re.fullmatch(re.escape(context.version['version']) + '/' + prefix + r'-[0-9]{3,}', identity) or
            reference['path'] != context.vr + '/release/' + identity.split('/')[1] + '.yaml' or
            (value['version'], value['delivery_line']) != (context.version['version'], context.version['delivery_line'])):
        raise CheckError('G4.owner', 'release artifact identity/path/Version/line disagree', refs=[reference])
    for revision in context.store.git('log', '--format=%H', reference['commit'], '--', reference['path']).decode().splitlines():
        if reference['path'] in context.store.tree(revision) and digest(context.store.read(revision, reference['path'])) != reference['sha256']:
            raise CheckError('G4.immutable', 'a new composition or decision needs a new ID; retain earlier qualification', refs=[reference])
    for revision in (context.snapshot['head_revision'], context.snapshot['metadata_revision']):
        if not context.store.ancestor(reference['commit'], revision):
            raise CheckError('G4.history', 'retain qualification artifacts before their selected metadata head')
        current_ref(context.store, reference, revision)
    return value


def candidate_inputs(context, candidate, *, engineering_review=None):
    store, target = context.store, context.snapshot['target_revision']
    if candidate['baseline_ref'] != context.snapshot['baseline_ref'] or candidate['code_revision'] != target:
        raise CheckError('G4.candidate-binding', 'candidate must select the current effective BL and actual target code')
    refs = {ref['path']: ref for ref in candidate['input_refs']}
    if len(refs) != len(candidate['input_refs']):
        raise CheckError('G4.inputs', 'candidate input paths must be unique')
    # The whole tracked engineering tree is the candidate denominator. Product
    # and harness metadata are protected separately by G1/current_engineering.
    needed = {path for path in store.tree(target)
              if not path.startswith(('requirements/', 'harness/version-requirements/')) and path != 'scripts/requirements-check'}
    if context.configuration['ui_design'] == 'enabled':
        from .runtime import reviewed_implementation
        from .ui_metadata import reviewed_metadata
        # Exempt only the verified installed tool and qualified passive design
        # files. Unknown files and explicitly built inputs keep their checks.
        needed.difference_update(reviewed_implementation(replace(context, content_commit=target)))
        if engineering_review is not None:
            needed.difference_update(reviewed_metadata(context, context.snapshot, engineering_review))
    if not needed <= refs.keys():
        raise CheckError('G4.inputs', 'candidate omits tracked engineering/spec/resource inputs', refs=sorted(needed - refs.keys()))
    for ref in refs.values():
        if ref['commit'] != target:
            raise CheckError('G4.input-revision', 'candidate engineering inputs must select its tested code commit')
        current_ref(store, ref, target)
    for key in ('dependencies_ref', 'configuration_ref'):
        if refs.get(candidate[key]['path']) != candidate[key]:
            raise CheckError('G4.input-identity', 'dependency/configuration identity must be a declared candidate input')
    build = validate('release_build', parse_json(evidence(store, candidate['build_ref'])))
    if engineering_review is not None:
        from .ui_metadata import reject_build_use
        reject_build_use(engineering_review, build['input_refs'])
    if (build['source_revision'] != target or
            set(map(canonical_bytes, build['input_refs'])) != set(map(canonical_bytes, candidate['input_refs']))):
        raise CheckError('G4.build-inputs', 'actual build receipt must select the complete candidate input set')
    if _time(build['finished_at']) < _time(build['started_at']):
        raise CheckError('G4.build-time', 'build cannot finish before it starts')
    evidence(store, build['artifact_ref'])
    evidence(store, build['log_ref'])
    unique(candidate['environments'], 'id', location='candidate environments')
    for row in candidate['environments']:
        for ref in (row['environment_ref'], row['data_ref'], row['deployment_target_ref'], *row['external_service_refs']):
            evidence(store, ref)
    return build


def delivery_receipts(delivery, candidate, control):
    """Recompute G3 receipts; an archived directory or saved PASS is insufficient."""
    required = set(delivery.allocations)
    required.update(edge['provider_ref'] for edge in delivery.edges.values()
                    if edge['active'] and edge['provider'] in delivery.candidates)
    supplied, receipts, seen_tasks = set(), [], set()
    for row in candidate['delivery_receipts']:
        selected = set(row['contributions'])
        if not selected <= required or supplied & selected:
            raise CheckError('G4.delivery-selection', 'receipt selections must partition required contributions')
        receipt = read_integrated_receipt(delivery.context, row['context_ref'], row['result_ref'], allow_alternatives=True)
        origin, proof = receipt['snapshot'], receipt['evidence']
        if origin['subject'].startswith(('task:', 'pr:')):
            if origin['subject'] in seen_tasks:
                raise CheckError('G4.delivery-selection', 'a task receipt cannot be selected twice')
            seen_tasks.add(origin['subject'])
            association = validate('tiny_association', parse_json(delivery.store.ref(origin['tiny_ref'])))
            if not selected and association['requirements']:
                raise CheckError('G4.delivery-selection', 'a business task cannot erase its selected contribution set')
        elif not selected:
            raise CheckError('G4.delivery-selection', 'only an actual task without R/AC can have an empty product contribution set')
        if (not delivery.store.ancestor(origin['target_revision'], candidate['code_revision']) or
                not delivery.store.ancestor(origin['control_revision'], delivery.context.snapshot['control_revision'])):
            raise CheckError('G4.delivery-history', 'delivery must belong to this candidate and retained control history')
        accepted = defaultdict(set)
        capabilities = set(proof.get('integrated_capabilities', []))
        if origin['subject'].startswith('change:'):
            accepted.update({key: set(value) for key, value in proof['integrated_acceptance'].items()})
            cid = origin['trace_ref']['path'].rsplit('/', 1)[1].removesuffix('.yaml')
            key = (origin['delivery_line'], origin['version'], cid)
            if key not in control.completed or control.completed[key]['reservation_ref'] != proof['reservation_ref']:
                raise CheckError('G4.delivery-unconfirmed', 'Standard delivery requires its actual successful capacity confirmation')
        else:
            for item in proof['delivery']['acceptance']:
                for contribution in item['contributions']:
                    accepted[contribution].add(item['acceptance'])
        identities = defaultdict(set)
        for expectation in origin.get('verification_inputs', []):
            record = validate('verification_record', parse_yaml(delivery.store.ref(expectation['verification_ref'])))
            for coverage in record['coverage']:
                if coverage['contribution'] in selected:
                    coverage_identity(delivery, coverage)
                    identities[coverage['contribution']].update(coverage.get('acceptance', []))
        for contribution in selected:
            if contribution in delivery.allocations:
                needed = delivery.allocations[contribution]['acceptance']
                if not needed <= accepted[contribution] or not needed <= identities[contribution]:
                    raise CheckError('G4.delivery-coverage', 'selected receipt did not actually accept this complete current contribution', refs=[contribution])
            elif contribution not in capabilities:
                raise CheckError('G4.delivery-coverage', 'technical contribution has no actual integrated delivery', refs=[contribution])
        supplied.update(selected)
        receipts.append({'subject': origin['subject'], **row})
    if supplied != required:
        raise CheckError('G4.delivery-missing', 'all current contributions require actual S6 delivery, including inherited/existing/external paths', refs=sorted(required - supplied))
    return receipts


def candidate_execution(context, candidate, expected, *, require_pass=True):
    identities = expected['identities']
    for key in ('build_ref', 'dependencies_ref', 'configuration_ref'):
        if identities[key] != candidate[key]:
            raise CheckError('G4.execution-identity', 'execution belongs to another build/dependency/configuration combination', refs=[key])
    if not any((row['environment_ref'], row['data_ref']) == (identities['environment_ref'], identities['data_ref'])
               for row in candidate['environments']):
        raise CheckError('G4.execution-environment', 'execution does not use a declared candidate environment/data identity')
    if expected['tested_revision'] != candidate['code_revision']:
        raise CheckError('G4.stale-execution', 'final evidence must test this actual candidate, not an ancestor or another line')
    checked = check_execution(context, expected['verification_ref'], tested_revision=candidate['code_revision'],
                              identities=identities, require_pass=require_pass,
                              engineering_review=context.read('reviews/engineering.yaml', 'review'))
    declared = set(map(canonical_bytes, candidate['input_refs']))
    if not set(map(canonical_bytes, checked['record']['input_refs'])) <= declared:
        raise CheckError('G4.execution-inputs', 'final execution declares inputs outside the fixed candidate engineering set')
    return checked


def version_verification(delivery, snapshot, candidate, *, ui_composition=None):
    # All final business ACs are completion obligations. Pure later release
    # prerequisites are non-final or technical plan rows, never hidden ACs.
    due = [row for row in delivery.plan['obligations'] if row['checkpoint'] != 'release' or
           snapshot['phase'] == 'release' or row.get('final')]
    refs = {canonical_bytes(ref): ref for row in due for ref in row['evidence_refs']}
    expected = {canonical_bytes(row['verification_ref']): row for row in snapshot['verification_inputs']}
    if len(expected) != len(snapshot['verification_inputs']) or not refs.keys() <= expected.keys():
        raise CheckError('G4.execution-selection', 'execution expectations must exactly cover all due plan evidence')
    # An actual task can have UI-only engineering behavior without a fake R
    # or verification-plan contribution. Its additional final E must identify
    # one of the independently selected, integrated current task associations.
    for key in expected.keys() - refs.keys():
        value = validate('verification_record', parse_yaml(delivery.store.ref(expected[key]['verification_ref'])))
        tasks = (ui_composition or {}).get('tasks', {})
        if not value.get('task_coverage') or any(row['subject'] not in tasks or
                row['tiny_ref'] != tasks[row['subject']]['reference'] for row in value['task_coverage']):
            raise CheckError('G4.execution-selection', 'extra final E must cover an actually selected current UI task')
    executions = {key: candidate_execution(delivery.context, candidate, expected[key]) for key in expected}
    for checked in executions.values():
        for coverage in checked['record']['coverage']:
            coverage_identity(delivery, coverage)
    accepted, links = defaultdict(set), []
    for row in due:
        if not row['evidence_refs']:
            raise CheckError('G4.unexecuted', 'due verification has not actually run', refs=[row['id']])
        needed = ({row['capability_ref']: set()} if 'capability_ref' in row else
                  {key: set(row['acceptance']) & delivery.allocations[key]['acceptance'] for key in row['contributions']})
        covered, technical = defaultdict(set), set()
        for ref in row['evidence_refs']:
            checked = executions[canonical_bytes(ref)]
            cases = set()
            for coverage in checked['record']['coverage']:
                key = coverage['contribution']
                if key not in needed:
                    continue
                cases.update(coverage['case_ids'])
                if 'requirement' in coverage:
                    covered[key].update(set(coverage['acceptance']) & needed[key])
                else:
                    technical.add(key)
            links.append({'obligation_id': row['id'], 'verification_ref': ref, 'case_ids': sorted(cases)})
        if any((acs and not acs <= covered[key]) or (key in delivery.capabilities and key not in technical)
               for key, acs in needed.items()):
            raise CheckError('G4.obligation-coverage', 'actual cases omit a required contribution or AC', refs=[row['id']])
        if row.get('final'):
            for ac in row['acceptance']:
                accepted[(row['requirement'], ac)].update(key for key in needed if ac in covered[key])
    for pair, required in delivery.coverage.items():
        if accepted[pair] != required:
            raise CheckError('G4.final-coverage', 'the entire effective scope, not just generated Changes, is the acceptance denominator', refs=list(pair))
    for environment in candidate['environments']:
        if environment['checkpoint'] == 'release' and snapshot['phase'] == 'completion':
            continue
        if not any((value['record']['identities']['environment_ref'], value['record']['identities']['data_ref']) ==
                   (environment['environment_ref'], environment['data_ref']) for value in executions.values()):
            raise CheckError('G4.environment-unexecuted', 'a due candidate environment has no actual passing execution', refs=[environment['id']])
    return {'acceptance': [{'requirement': uid, 'acceptance': ac, 'contributions': sorted(accepted[(uid, ac)])}
                           for uid, ac in sorted(delivery.coverage)],
            'verification_links': links, 'deferred_obligations': [row['id'] for row in delivery.plan['obligations'] if row not in due]}, executions


def version_conditions(delivery, snapshot, verified, executions):
    assessments = assessment_scope(delivery)
    states = []
    for eid, edge in delivery.edges.items():
        entry = edge['entry']
        state = 'not-applicable' if not edge['active'] else 'reviewed-soft' if entry['strength'] == 'soft' else 'due'
        if state == 'due' and entry['checkpoint'] == 'release' and snapshot['phase'] == 'completion':
            state = 'not-due'
        if state == 'due':
            assessment = assessments.get(eid)
            if assessment is None or assessment['conclusion'] != 'available' or assessment['target_revision'] != snapshot['target_revision']:
                raise CheckError('G4.dependency', 'due hard dependency requires current candidate availability', refs=[eid])
            contract = provider_contract(delivery, edge, assessment)
            current_ref(delivery.store, contract, snapshot['target_revision'])
            if edge['provider'] in delivery.endpoints and delivery.endpoints[edge['provider']]['target_line_path'] == 'port-planned':
                raise CheckError('G4.dependency', 'a planned target-line port is not available', refs=[eid])
            # S3's available label is only a reviewed assessment. Reuse the
            # existing reader to prove its selected current provider execution,
            # exact contract and (for a candidate) actual integration receipt.
            provider_evidence(delivery, edge, assessment, snapshot['target_revision'])
            tagged = [row for row in delivery.plan['obligations'] if eid in row.get('edge_refs', [])]
            # Implementation-only availability was admitted at S5/S6. For
            # integration/release, require actual provider+consumer combination.
            if entry['kind'] in ('integration', 'release') and not tagged:
                raise CheckError('G4.dependency', 'due combination dependency lacks verification responsibility', refs=[eid])
            for row in tagged:
                coverage, technical = defaultdict(set), set()
                for ref in row['evidence_refs']:
                    checked = executions.get(canonical_bytes(ref))
                    if checked is None or not any((item['path'], item['sha256']) == (contract['path'], contract['sha256']) for item in checked['record']['input_refs']):
                        raise CheckError('G4.dependency-input', 'combination execution omits its actual provider contract', refs=[eid])
                    for item in checked['record']['coverage']:
                        coverage[item['contribution']].update(item.get('acceptance', []))
                        if 'capability' in item:
                            technical.add(item['contribution'])
                needed = {key: delivery.allocations[key]['acceptance'] for key in edge['consumers'] if key in delivery.allocations}
                needed[edge['provider_ref']] = edge['provider_acceptance']
                if any((acs and not set(acs) <= coverage[key]) or (key in delivery.capabilities and key not in technical) for key, acs in needed.items()):
                    raise CheckError('G4.dependency-coverage', 'provider-only or local evidence cannot prove the required combination', refs=[eid])
            state = 'satisfied'
        states.append({'edge': eid, 'state': state})
    return states


def issue_and_control_checks(delivery, questions, control, snapshot, receipts):
    subjects = {'version:' + snapshot['version']}
    for uid, ac in delivery.coverage:
        subjects.update({'requirement:' + snapshot['version'] + '/' + uid, 'scope:' + snapshot['version'] + '/' + uid + '/' + ac})
    subjects.update('candidate:' + snapshot['version'] + '/' + cid for cid in delivery.active)
    # Broad scope queries are expanded to the existing Version/R/AC control
    # identities above; they are not themselves published control targets.
    subjects.update(row['subject'] for row in receipts if not row['subject'].startswith('scope:'))
    for entry in ('propose', 'apply', 'merge') + (('release',) if snapshot['phase'] == 'release' else ()):
        control.holds.require_clear(line=snapshot['delivery_line'], entry=entry, subjects=subjects)
    for key, rc in control.changes.records.items():
        if key[:2] == (snapshot['delivery_line'], snapshot['version']) and rc['status'] not in ('rejected', 'withdrawn', 'verified'):
            raise CheckError('G4.rc-unverified', 'necessary Requirement Change disposition is incomplete', refs=[rc['latest_ref']])
    for identity, impact in questions.impacts.items():
        value = questions.resolve(identity)
        blockers = impact['blocking_for']
        due = bool(blockers - {'release'}) or ('release' in blockers and snapshot['phase'] == 'release')
        if due:
            excluded = (value['status'] == 'deferred' and blockers <= {'baseline'} and
                        not impact['affected_requirements'] & delivery.requirements.records.keys())
            questions.require_resolved(identity, scope_decision=excluded)
        elif value['status'] != 'resolved' and not ('release' in blockers and snapshot['phase'] == 'completion'):
            if value['status'] != 'deferred' or value['response'] is None:
                raise CheckError('G4.issue-disposition', 'nonblocking open matters require an explicit accepted disposition and owner', refs=[identity])
            decision(questions.context, value['response'])


def qualification_reviews(context, snapshot, candidate, record, questions, executions, *, ui_composition=None):
    roles = {'engineering-owner', 'product-owner', 'qa-owner'}
    required = [snapshot['release_candidate_ref'], snapshot['baseline_ref'], *snapshot['engineering_inputs'].values(),
                *candidate['input_refs'], candidate['build_ref']]
    required.extend(ref for receipt in candidate['delivery_receipts'] for ref in (receipt['context_ref'], receipt['result_ref']))
    required.extend(row['verification_ref'] for row in snapshot['verification_inputs'])
    from .ui_completion import review_refs as ui_refs, CHECKS as UI_CHECKS
    required.extend(ui_refs(ui_composition))
    required = list({canonical_bytes(ref): ref for ref in required}.values())
    actors, reviewed = set(), set()
    latest_execution = max(_time(item['record']['finished_at']) for item in executions.values())
    review_times = []
    checks = COMPLETION_CHECKS + (RELEASE_CHECKS if snapshot['phase'] == 'release' else ()) + (UI_CHECKS if ui_composition else ())
    for ref in record['reviews']:
        if not ref['path'].startswith(context.vr + '/reviews/delivery/'):
            raise CheckError('G4.review-path', 'Version acceptance uses the existing delivery Review namespace')
        current_ref(context.store, ref, snapshot['metadata_revision'])
        view = replace(context, content_commit=ref['commit'])
        review = check_review(view, ref['path'][len(context.vr) + 1:], 'delivery', (), roles=roles,
                              required_refs=required, required_checks=checks)
        if review['pending_units'] or _time(review['at']) < latest_execution:
            raise CheckError('G4.acceptance-time', 'final acceptance cannot precede its actual executions or leave reading pending')
        for issue in set(review['issue_refs']) | {issue for check in review['checks'] for issue in check['issue_refs']}:
            questions.resolve(issue)
        review_times.append(_time(review['at']))
        if review['role'] in reviewed or review['actor'] in actors:
            raise CheckError('G4.independent-review', 'product, engineering and QA must supply distinct named acceptance reviews')
        reviewed.add(review['role']); actors.add(review['actor'])
    if reviewed != roles:
        raise CheckError('G4.acceptance', 'Version Completion needs product, engineering and QA acceptance')
    if snapshot['phase'] == 'release':
        if record['authorization'] is None:
            raise CheckError('G4.release-authorization', 'release needs the explicitly declared release owner decision')
        # The existing named integrator can carry an explicit release mandate;
        # a dedicated release owner is optional, not a forced product rebaseline.
        decision(context, record['authorization'], roles={'release-owner', 'integrator'})
        if _time(record['authorization']['at']) < max(review_times):
            raise CheckError('G4.release-authorization', 'release authorization must follow the selected candidate acceptance')
    elif record['authorization'] is not None:
        raise CheckError('G4.completion-only', 'completion does not authorize release')


def release_confirmation(context, snapshot, candidate, build, release_decision):
    reference = snapshot.get('release_observation_ref')
    if reference is None:
        return 'ready-to-release'
    record = retained_record(context, reference, 'release_observation', 'observation')
    for key in ('candidate_ref', 'decision_ref'):
        if record[key] != snapshot['release_' + key]:
            raise CheckError('G4.release-binding', 'actual release must retain the qualified candidate and explicit decision')
    if record['build_ref'] != candidate['build_ref'] or not any(row['deployment_target_ref'] == record['deployment_target_ref'] for row in candidate['environments']):
        raise CheckError('G4.release-target', 'release build and deployment target differ from the qualified combination')
    operation = validate('release_operation', parse_json(evidence(context.store, record['operation_ref'])))
    if _time(operation['started_at']) < _time(release_decision['authorization']['at']):
        raise CheckError('G4.release-authorization-time', 'actual release must start after its explicit candidate authorization')
    for key in ('candidate_ref', 'decision_ref', 'build_ref', 'deployment_target_ref', 'finished_at'):
        if operation[key] != record[key]:
            raise CheckError('G4.release-operation', 'release confirmation relabels its actual operation')
    evidence(context.store, operation['log_ref'])
    if operation['artifact_ref'] != build['artifact_ref']:
        raise CheckError('G4.release-artifact', 'actual release operation must identify the qualified build artifact')
    if (_time(operation['finished_at']) < _time(operation['started_at']) or
            operation['actor'] not in context.version['owners'].values()):
        raise CheckError('G4.release-operation', 'release operation actor or timing is invalid')
    decision(context, record['confirmation'], roles={'integrator', 'release-owner'})
    if (record['outcome'] == 'succeeded') != (operation['exit_code'] == 0):
        raise CheckError('G4.release-result', 'reported release outcome differs from the actual operation exit')
    if _time(record['confirmation']['at']) < _time(record['finished_at']):
        raise CheckError('G4.release-confirmation', 'confirmation cannot precede the actual release operation')
    if record['outcome'] != 'succeeded' or operation['exit_code'] != 0:
        raise CheckError('G4.release-failed', 'actual release failed; retain earlier completion and follow the team recovery process')
    if not record['post_verification_inputs']:
        raise CheckError('G4.post-release', 'successful operation still requires actual post-release confirmation')
    for expected in record['post_verification_inputs']:
        checked = candidate_execution(context, candidate, expected)
        if _time(checked['record']['started_at']) < _time(record['finished_at']):
            raise CheckError('G4.post-release', 'pre-release evidence cannot masquerade as post-release verification')
        if _time(record['confirmation']['at']) < _time(checked['record']['finished_at']):
            raise CheckError('G4.release-confirmation', 'released confirmation must follow its actual post-release checks')
        if not any(row['deployment_target_ref'] == record['deployment_target_ref'] and
                   row['environment_ref'] == expected['identities']['environment_ref'] for row in candidate['environments']):
            raise CheckError('G4.post-release', 'post-release verification must observe the actual deployment target')
    return 'released'


def check_version(store, snapshot):
    context = resolve(store, snapshot)
    if not snapshot['control_revision'] or any(key not in snapshot for key in ('engineering_inputs', 'verification_inputs', 'release_candidate_ref', 'release_decision_ref')):
        raise CheckError('G4.context', 'Version qualification requires the candidate, decision, current engineering/verification inputs and control')
    if not store.ancestor(snapshot['target_revision'], snapshot['head_revision']):
        raise CheckError('G4.history', 'later evidence must descend from the actual candidate code')
    baseline, checked = baseline_context(store, snapshot)
    current = current_engineering(baseline, snapshot, snapshot['engineering_inputs'])
    for revision in {snapshot['metadata_revision'], snapshot['head_revision'], snapshot['target_revision'], current.content_commit}:
        preserved_inputs(baseline, revision, checked)
    candidate = retained_record(context, snapshot['release_candidate_ref'], 'release_candidate', 'candidate')
    if snapshot['subject'] != 'release-candidate:' + candidate['id']:
        raise CheckError('G4.subject', 'snapshot must select the actual Version release candidate')
    build = candidate_inputs(current, candidate, engineering_review=current.read('reviews/engineering.yaml', 'review'))
    record = retained_record(context, snapshot['release_decision_ref'], 'release_decision', 'decision')
    if record['candidate_ref'] != snapshot['release_candidate_ref'] or record['phase'] != snapshot['phase']:
        raise CheckError('G4.decision-binding', 'acceptance decision belongs to another candidate or phase')
    requirements = RequirementIndex(baseline)
    requirements.check_content()
    delivery = DeliveryIndex(requirements, engineering_context=current, map_ref=snapshot['engineering_inputs']['map_ref'],
                             verification_plan_ref=snapshot['engineering_inputs']['verification_plan_ref'])
    if delivery.map['baseline'] != baseline.baseline['id']:
        raise CheckError('G4.baseline', 'current delivery obligations must retain the selected effective baseline')
    delivery.check(); check_feasibility(delivery)
    scope = ReviewScope(requirements, delivery)
    engineering = scope.check_engineering()
    scope.engineering_questions.check_baseline(requirements.records)
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    receipts = delivery_receipts(delivery, candidate, control)
    from .ui_completion import prepare as prepare_ui, execution_coverage
    ui = prepare_ui(delivery, snapshot, candidate, receipts)
    verified, executions = version_verification(delivery, snapshot, candidate, ui_composition=ui)
    ui = execution_coverage(delivery, ui, snapshot['verification_inputs'], executions)
    conditions = version_conditions(delivery, snapshot, verified, executions)
    issue_and_control_checks(delivery, scope.engineering_questions, control, snapshot, receipts)
    qualification_reviews(current, snapshot, candidate, record, scope.engineering_questions, executions, ui_composition=ui)
    state = release_confirmation(current, snapshot, candidate, build, record) if snapshot['phase'] == 'release' else 'complete'
    if state == 'released' and ui:
        from .ui_integration import execution_inputs
        observation = validate('release_observation', parse_yaml(store.ref(snapshot['release_observation_ref'])))
        for entry in ui['entries']:
            execution_inputs(delivery, entry['ui'], observation['post_verification_inputs'])
    refs = References(current)
    for value in (snapshot, candidate, record, engineering, verified):
        refs.fixed(value)
    pins = retain_inputs(baseline, [snapshot[key] for key in ('metadata_revision', 'head_revision', 'target_revision')])
    if snapshot['evaluation_mode'] == 'current':
        live = capture(store, extra_roots=['openspec'])
        if live.record['base_revision'] != snapshot['head_revision'] or live.record['changes']:
            raise CheckError('G4.uncommitted-inputs', 'qualification needs its actual clean evidence metadata head')
        live.assert_current(store)
    resolve(store, snapshot)
    return {'rule_id': 'G4.' + snapshot['phase'], 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'candidate_ref': snapshot['release_candidate_ref'], 'decision_ref': snapshot['release_decision_ref'],
                         'release_observation_ref': snapshot.get('release_observation_ref'),
                         'baseline_ref': snapshot['baseline_ref'], 'code_revision': candidate['code_revision'],
                         'build_ref': candidate['build_ref'], 'artifact_ref': build['artifact_ref'],
                         'current_qualification': snapshot['evaluation_mode'] == 'current',
                         'release_ready': snapshot['evaluation_mode'] == 'current' and state == 'ready-to-release',
                         'qualification': state, 'acceptance': verified, 'conditions': conditions,
                         'delivery_receipts': receipts, 'retained_pins': pins,
                         'ui': ui,
                         'scope': 'fixed candidate qualification only; does not execute a release or grant another action'},
            'next_owner': 'release-owner' if snapshot['phase'] == 'completion' else 'integrator'}
