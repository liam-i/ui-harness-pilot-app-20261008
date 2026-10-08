"""AC/contribution links to one actual Change's planning artifacts.

Trace keeps references, never a second copy of specs, task text or task state.
The surrounding Gate still owns publication, current control and authorization.
"""
from collections import defaultdict
from dataclasses import replace

from .assets import AssetIndex
from .core import canonical_bytes, digest, parse_json, parse_yaml
from .errors import CheckError, InputError
from .markdown_source import parse_document, resolve_link
from .models import validate
from .openspec_artifacts import read_observation, tasks
from .reviews import check_review, evidence
from .worktree import reviewed_execution_inputs


def file_ref(reference):
    return {k: reference[k] for k in ('commit', 'path', 'sha256')}


def spec_target(store, row, observation, revision):
    ref = row['file_ref']
    raw = store.ref(ref)
    store.read(revision, ref['path'], ref['sha256'])
    delta = ref['path'] in observation['artifacts']['specs']
    main = ref['path'].startswith('openspec/specs/') and ref['path'].endswith('/spec.md')
    if not delta and not main:
        raise CheckError('trace.spec-location', 'Spec locator does not select an actual Delta or main capability Spec', refs=[ref])
    headings = parse_document(raw)['headings']
    requirements = [h for h in headings if h['level'] == 3 and h['title'] == 'Requirement: ' + row['requirement_title']]
    if len(requirements) != 1:
        raise CheckError('trace.spec-requirement', 'Requirement title is absent or ambiguous in the fixed Spec', refs=[row])
    requirement = requirements[0]
    scenarios = [h for h in headings if h['level'] == 4 and h['title'] == 'Scenario: ' + row['scenario_title'] and
                 requirement['start'] < h['start'] <= requirement['section_end']]
    if len(scenarios) != 1:
        raise CheckError('trace.spec-scenario', 'Scenario does not belong to the selected Requirement', refs=[row])
    return {'file_ref': ref, 'requirement_lines': [requirement['start'], requirement['section_end']],
            'scenario_lines': [scenarios[0]['start'], scenarios[0]['section_end']]}


def check_links(delivery, trace, observation, revision):
    cid, store = trace['candidate_id'], delivery.store
    allocations = {k: v for k, v in delivery.allocations.items() if v['node'] == cid}
    capabilities = {k: v for k, v in delivery.capabilities.items() if v['node'] == cid}
    obligations = {o['id']: o for o in delivery.plan['obligations']}
    required_capabilities = ({e['provider_ref'] for e in delivery.edges.values() if e['active']} |
                             {o['capability_ref'] for o in obligations.values() if 'capability_ref' in o}) & capabilities.keys()
    coverage, technical, selected, required_refs = defaultdict(set), set(), [], []
    for row in trace['links']:
        contribution = row['contribution']
        allocation, capability = allocations.get(contribution), capabilities.get(contribution)
        if allocation is None and capability is None:
            raise CheckError('trace.contribution', 'Trace links an unallocated or different candidate contribution', refs=[contribution])
        if allocation is not None:
            if not row['acceptance'] or not set(row['acceptance']) <= allocation['acceptance']:
                raise CheckError('trace.acceptance', 'Trace must name exact allocated ACs', refs=[row])
            if not row['specs']:
                raise CheckError('trace.business-spec', 'business AC needs an actual behavior Spec/Scenario; no-Delta may use the correct main Spec')
            coverage[contribution].update(row['acceptance'])
            required_refs.extend((allocation['info']['record_ref'], allocation['info']['configuration_ref']))
        else:
            if row['acceptance']:
                raise CheckError('trace.technical-ac', 'technical contribution cannot invent business AC IDs')
            technical.add(contribution)
        if not set(row['tasks']) <= observation['tasks'].keys():
            raise CheckError('trace.task', 'stable displayed Task ID is missing from the actual tracked file', refs=[row])
        responsibility = set()
        for oid in row['verification_obligations']:
            obligation = obligations.get(oid)
            if obligation is None:
                raise CheckError('trace.verification', 'Trace names an absent verification obligation', refs=[oid])
            if capability is not None:
                if obligation.get('capability_ref') != contribution:
                    raise CheckError('trace.verification', 'verification responsibility belongs to another capability', refs=[oid])
                responsibility.add(contribution)
            else:
                info = allocation['info']
                if (obligation.get('requirement') != info['uid'] or obligation.get('revision') != info['value']['revision'] or
                        contribution not in obligation.get('contributions', [])):
                    raise CheckError('trace.verification', 'verification responsibility differs from this R revision/contribution', refs=[oid])
                responsibility.update(set(obligation['acceptance']) & set(row['acceptance']))
        expected = set(row['acceptance']) if allocation is not None else {contribution}
        if responsibility != expected:
            raise CheckError('trace.verification-coverage', 'actual verification obligations do not cover this Trace row', refs=[row])
        specs = [spec_target(store, spec, observation, revision) for spec in row['specs']]
        required_refs.extend(spec['file_ref'] for spec in row['specs'])
        selected.append({'contribution': contribution, 'acceptance': row['acceptance'], 'specs': specs,
                         'tasks': row['tasks'], 'verification_obligations': row['verification_obligations']})
    if any(coverage[k] != v['acceptance'] for k, v in allocations.items()) or not required_capabilities <= technical:
        raise CheckError('trace.coverage', 'Trace does not account for every selected candidate AC and technical contribution')
    return selected, required_refs


def check_asset_uses(delivery, trace, observation, revision, *, registry_ref=None, relocations=None):
    from .change_assets import check_registered_outputs

    assets = AssetIndex(delivery.context, sources=delivery.requirements.sources)
    uses, refs = [], []
    registered = check_registered_outputs(assets, trace, observation, revision,
                                          registry_ref=registry_ref, relocations=relocations)
    for value in registered:
        refs.extend(value[key] for key in ('content_ref', 'received_ref', 'manifest_ref', 'location_ref'))
    relocations = relocations or {}
    for row in trace['asset_uses']:
        contribution = row['contribution']
        allocation = delivery.allocations.get(contribution)
        capability = delivery.capabilities.get(contribution)
        item = allocation or capability
        if item is None or item['node'] != trace['candidate_id']:
            raise CheckError('trace.asset-consumer', 'asset use must belong to this candidate contribution')
        if isinstance(row['use']['ref'], str):
            raise CheckError('trace.asset-reference', 'engineering usage requires fixed owner references, not an ambiguous source shorthand')
        value = assets.resolve_use(row['use'], acceptance=allocation['acceptance'] if allocation else None)
        target = value['content_ref']
        original = target
        target = relocations.get(target['path'], target)
        if (target['sha256'] != original['sha256'] or
                (target['path'].startswith(observation['change_root'] + '/assets/') and value['identity'] is None)):
            raise CheckError('trace.asset-identity', 'Change-derived use requires its registered identity and unchanged actual bytes')
        refs.append(target)
        for key in ('manifest_ref', 'received_ref'):
            if key in value:
                refs.append(value[key])
        for locator in row['used_in']:
            raw = delivery.store.ref(locator)
            if locator['path'] in observation['artifacts']['tasks']:
                current = delivery.store.read(revision, locator['path'])
                if tasks(raw)[1] != tasks(current)[1]:
                    raise CheckError('trace.asset-artifact-stale', 'asset usage points to changed Task planning content; state and fixed evidence navigation do not change planning', refs=[locator])
            else:
                delivery.store.read(revision, locator['path'], locator['sha256'])
            files = {p for paths in observation['artifacts'].values() for p in paths}
            if locator['path'] not in files:
                raise CheckError('trace.asset-location', 'planning asset use must locate the actual Spec/Design/Proposal/Tasks')
            parsed = parse_document(raw)
            matched = False
            for link in parsed['links']:
                resolved = resolve_link(locator['path'], link['parsed_target'], delivery.store.tree(revision), {})
                if resolved['path'] == target['path'] and resolved['status'] == 'resolved':
                    delivery.store.read(revision, target['path'], target['sha256'])
                    matched = True
            if not matched:
                raise CheckError('trace.asset-link', 'Artifact lacks a resolvable link to the selected fixed asset bytes', refs=[locator, target])
            refs.append(locator)
        uses.append(value)
    return uses, refs


def check_planning_trace(delivery, reference, snapshot, payload, *, require_review=True, allow_task_progress=False):
    store = delivery.store
    trace = validate('planning_trace', parse_yaml(evidence(store, reference)))
    cid = payload['candidate_id']
    path = delivery.context.vr + '/trace/changes/' + cid + '.yaml'
    if (reference['path'] != path or trace['candidate_id'] != cid or trace['version'] != snapshot['version'] or
            trace['delivery_line'] != snapshot['delivery_line'] or trace['baseline_ref'] != snapshot['baseline_ref'] or
            trace['dispatch_ref'] != snapshot['dispatch_ref'] or
            trace['change'] != delivery.candidates[cid]['change_name']):
        raise CheckError('trace.identity', 'Trace, current map, baseline, Version/line and exact published event disagree')
    for revision in {snapshot['metadata_revision'], snapshot['head_revision']}:
        store.read(revision, path, reference['sha256'])
    # A retry may update locators/links, but cannot reassign the logical delivery.
    for commit in store.git('log', '--format=%H', snapshot['metadata_revision'], '--', path).decode().splitlines():
        if path in store.tree(commit):
            old = parse_yaml(store.read(commit, path))
            if any(old.get(k) != trace[k] for k in ('candidate_id', 'version', 'delivery_line', 'change')):
                raise CheckError('trace.identity-history', 'existing Trace was reassigned instead of resuming its original Change')
    observation = read_observation(store, trace['observation_ref'], change=trace['change'],
                                   actual_revision=snapshot['head_revision'], allow_task_progress=allow_task_progress)
    if observation['planning_digest'] != trace['planning_digest']:
        raise CheckError('trace.planning-digest', 'Trace does not bind the actual current planning content')
    evidence(store, trace['design']['evidence_ref'])
    expected = 'present' if observation['design_present'] else 'not-required'
    if trace['design']['disposition'] != expected:
        raise CheckError('trace.design', 'Design applicability decision differs from actual files')
    linked, refs = check_links(delivery, trace, observation, snapshot['head_revision'])
    assets, asset_refs = check_asset_uses(delivery, trace, observation, snapshot['head_revision'], registry_ref=reference)
    refs.extend(asset_refs)
    refs.extend([reference, trace['observation_ref'], trace['design']['evidence_ref'], *observation['input_refs']])
    observation_record = parse_json(store.ref(trace['observation_ref']))
    refs.append(observation_record['schema_ref'])
    # The original capture carries JSON, whose full reference already binds the
    # individual raw CLI results. Read them in read_observation, not a shadow plan.
    required = {canonical_bytes(r): r for r in refs}
    contextual = [snapshot['baseline_ref'], file_ref(snapshot['dispatch_ref']), payload['map_ref'],
                  payload['verification_plan_ref'], payload['engineering_review_ref'], *payload['context_refs']]
    execution_inputs = None
    checks = ('scope-coverage', 'artifact-consistency', 'design-applicability',
              'verification-obligations', 'input-applicability', 'asset-uses')
    from .ui_integration import review_refs, CHECKS
    ui_refs = review_refs(delivery)
    contextual.extend(ui_refs)
    if ui_refs:
        checks += CHECKS
    if snapshot.get('planning_inputs_ref') is not None:
        execution_inputs = reviewed_execution_inputs(store, snapshot, observation)
        contextual.extend([snapshot['apply_origin_ref'], snapshot['planning_inputs_ref']])
        checks += ('update-impact', 'execution-state')
    review, review_ref = None, None
    if require_review:
        context = replace(delivery.context, content_commit=snapshot['metadata_revision'])
        relative = 'reviews/planning/' + cid + '.yaml'
        review = check_review(context, relative, 'planning', (), roles={'engineering-owner'},
            required_refs=required.values(), required_context_refs=contextual,
            required_checks=checks)
        review_path = context.vr + '/' + relative
        store.read(snapshot['head_revision'], review_path, digest(store.read(context.content_commit, review_path)))
        review_ref = {'commit': context.content_commit, 'path': review_path,
                      'sha256': digest(store.read(context.content_commit, review_path))}
    return {'trace': trace, 'observation': observation, 'links': linked, 'assets': assets, 'review': review,
            'review_ref': review_ref,
            'required_refs': list(required.values()), 'required_context_refs': contextual,
            'required_checks': checks, 'execution_inputs': execution_inputs}
