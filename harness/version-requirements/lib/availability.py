"""Current contribution availability, separate from S3 feasibility and reservation.

An engineering assessment binds the expected execution context. E supplies the
actual observation. Neither a map edge nor an assessment's conclusion alone is
proof of delivery. Candidate providers additionally replay their actual
integrated Trace on this target; capacity release remains independent.
"""
from .core import canonical_bytes
from .errors import CheckError
from .models import unique
from .reviews import evidence
from .verification import check_execution


def provider_contract(delivery, edge, assessment):
    if edge['provider'] in delivery.candidates:
        selected = assessment.get('provider_integration')
        if selected is None:
            raise CheckError('availability.candidate-integration-required', 'candidate provider requires its actual integrated input/result and consumed contract', refs=[edge['entry']['id']])
        return selected['contract_ref']
    if 'provider_integration' in assessment:
        raise CheckError('availability.provider-kind', 'existing/external endpoints use their own evidence, not another candidate integration')
    return delivery.endpoints[edge['provider']]['contract_ref']


def candidate_executions(delivery, edge, assessment, target):
    from .integrated_receipt import read_integrated_receipt
    from .delivery_trace import current_ref

    selected = assessment['provider_integration']
    receipt = read_integrated_receipt(delivery.context, selected['context_ref'], selected['result_ref'])
    origin, proof = receipt['snapshot'], receipt['evidence']
    provider = edge['provider']
    if (origin['target_revision'] != target or origin['baseline_ref'] != delivery.context.snapshot['baseline_ref'] or
            proof['trace_ref']['path'] != delivery.context.vr + '/trace/changes/' + provider + '.yaml' or
            proof['change'] != delivery.candidates[provider]['change_name']):
        raise CheckError('availability.candidate-context', 'candidate proof must select this effective baseline, candidate and actual target; reassess stale integration before release')
    if not delivery.store.ancestor(origin['control_revision'], delivery.context.snapshot['control_revision']):
        raise CheckError('availability.candidate-control', 'current control must retain the provider integration history')
    if ((edge['provider_ref'] in delivery.allocations and
         not edge['provider_acceptance'] <= set(proof['integrated_acceptance'].get(edge['provider_ref'], []))) or
            (edge['provider_ref'] in delivery.capabilities and edge['provider_ref'] not in proof['integrated_capabilities'])):
        raise CheckError('availability.coverage', 'the required contribution must actually be accepted by the provider integration, not merely mentioned in an E')
    contract = selected['contract_ref']
    current_ref(delivery.store, contract, target)
    if contract not in assessment['observed_refs']:
        raise CheckError('availability.contract-observation', 'current assessment must explicitly observe the consumed provider contract')
    # Only E/case associations actually accepted by the provider's single
    # integrated Trace can discharge this edge. Archive or an unrelated E
    # cannot substitute for that completed contribution.
    selected_cases = {}
    for row in proof['delivery']['verification_links']:
        if edge['provider_ref'] in row['contributions']:
            selected_cases.setdefault(canonical_bytes(row['verification_ref']), set()).update(row['case_ids'])
    expectations = {canonical_bytes(row['verification_ref']): row for row in origin['verification_inputs']}
    executions = []
    for item in assessment['executions']:
        key = canonical_bytes(item['verification_ref'])
        expected = expectations.get(key)
        if key not in selected_cases or expected is None or item['identities'] != expected['identities']:
            raise CheckError('availability.candidate-evidence', 'select the exact E and execution identity accepted for this provider contribution')
        checked = check_execution(delivery.context, item['verification_ref'], tested_revision=expected['tested_revision'], identities=item['identities'], engineering_review=delivery.review)
        record = checked['record']
        if not any(ref['path'] == contract['path'] and ref['sha256'] == contract['sha256'] for ref in record['input_refs']):
            raise CheckError('availability.contract-input', 'provider execution must actually include the consumed contract')
        for ref in record['input_refs']:
            current_ref(delivery.store, ref, target)
        executions.append((item, checked, selected_cases[key]))
    return executions


def assessment_scope(delivery):
    """Structural S3 check only; future unknown availability may remain explicit."""
    engineering = delivery.review['engineering']
    rows = unique(engineering.get('availability', []), 'edge_id', location='engineering availability')
    for eid, row in rows.items():
        if eid not in delivery.edges:
            raise CheckError('availability.edge', 'assessment references an absent delivery edge', refs=[eid])
        if row['target_revision'] != engineering['code_ref']['commit']:
            raise CheckError('availability.target', 'assessment must select this engineering Review target', refs=[eid])
        evidence(delivery.store, row['assessment_ref'])
        for ref in row['observed_refs']:
            if ref['commit'] != row['target_revision']:
                raise CheckError('availability.observation', 'observed engineering inputs must belong to the assessment target', refs=[eid, ref])
            delivery.store.ref(ref)
        if row['conclusion'] == 'available' and (not row['executions'] or not row['observed_refs']):
            raise CheckError('availability.evidence-required', 'an available conclusion needs actual executions and observed inputs', refs=[eid])
        refs = [canonical_bytes(item['verification_ref']) for item in row['executions']]
        if len(refs) != len(set(refs)):
            raise CheckError('availability.duplicate-evidence', 'an assessment cannot repeat the same execution', refs=[eid])
    return rows


def provider_evidence(delivery, edge, assessment, target):
    store, provider = delivery.store, edge['provider']
    candidate = provider in delivery.candidates
    endpoint = None if candidate else delivery.endpoints[provider]
    if endpoint is not None and endpoint['target_line_path'] == 'port-planned':
        raise CheckError('availability.target-path', 'planned port is not current target-line availability', refs=[edge['entry']['id']])
    # The reviewed endpoint contract must be present on the actual target. A
    # contract belonging only to a feature/maintenance branch is insufficient.
    contract = provider_contract(delivery, edge, assessment)
    store.read(target, contract['path'], contract['sha256'])
    identity = (lambda ref: (ref['path'], ref['sha256'])) if candidate else canonical_bytes
    observed = {identity(ref) for ref in assessment['observed_refs']}
    covered, capability, executions = set(), False, []
    selected = candidate_executions(delivery, edge, assessment, target) if candidate else []
    if not candidate:
        for item in assessment['executions']:
            if item['verification_ref'] not in endpoint['availability_refs']:
                raise CheckError('availability.endpoint-evidence', 'assessment must select the endpoint evidence fixed by the current map', refs=[edge['entry']['id'], item['verification_ref']])
            checked = check_execution(delivery.context, item['verification_ref'], tested_revision=target, identities=item['identities'], engineering_review=delivery.review)
            selected.append((item, checked, set(checked['cases'])))
    for item, checked, accepted_cases in selected:
        ref = item['verification_ref']
        record = checked['record']
        if not {identity(ref) for ref in record['input_refs']} <= observed:
            raise CheckError('availability.input-scope', 'engineering assessment omits declared execution inputs', refs=[record['id']])
        for row in record['coverage']:
            if row['contribution'] != edge['provider_ref'] or not set(row['case_ids']) <= accepted_cases:
                continue
            if edge['provider_ref'] in delivery.allocations:
                allocation = delivery.allocations[edge['provider_ref']]
                info = allocation['info']
                if ('requirement' not in row or row['requirement'] != info['uid'] or row['revision'] != info['value']['revision'] or
                        row['record_ref'] != info['record_ref'] or row['configuration_ref'] != info['configuration_ref'] or
                        not set(row['acceptance']) <= allocation['acceptance']):
                    raise CheckError('availability.coverage-scope', 'execution contribution differs from the exact allocated R/configuration/AC', refs=[record['id'], edge['provider_ref']])
                covered.update(row['acceptance'])
            else:
                expected = delivery.capabilities[edge['provider_ref']]['capability']
                if row.get('capability') != expected:
                    raise CheckError('availability.coverage-scope', 'execution does not select this technical capability', refs=[record['id']])
                capability = True
        executions.append({'verification_ref': ref, 'cases': checked['cases'], 'counts': checked['counts']})
    if (edge['provider_ref'] in delivery.allocations and not edge['provider_acceptance'] <= covered) or (
            edge['provider_ref'] in delivery.capabilities and not capability):
        raise CheckError('availability.coverage', 'current executions do not cover the required provider contribution', refs=[edge['entry']['id']])
    return executions


def implementation_state(delivery, eid, assessments, target):
    """One fixed edge observation, shared by admission and readonly reports."""
    edge = delivery.edges[eid]
    entry = edge['entry']
    state = {'edge': eid, 'provider': edge['provider_ref'], 'state': 'not-due'}
    if not edge['active']:
        state['state'] = 'not-applicable'
    elif entry['strength'] == 'soft':
        state['state'] = 'reviewed-soft'
    elif entry['kind'] == 'implementation':
        row = assessments.get(eid)
        if row is None or row['conclusion'] == 'unknown':
            state['state'] = 'unknown'
        else:
            if row['target_revision'] != target:
                raise CheckError('availability.stale-target', 'current release differs from the assessed target', refs=[eid])
            state.update(assessment_ref=row['assessment_ref'], reason=row['reason'])
            if row['conclusion'] == 'unavailable':
                state['state'] = 'unsatisfied'
            else:
                state['executions'] = provider_evidence(delivery, edge, row, target)
                state['state'] = 'satisfied'
    return state


def implementation_dependencies(delivery, cid, payload, target, *, consumer_contributions=None):
    assessments = assessment_scope(delivery)
    states, unavailable, unknown = [], [], []
    for eid, edge in delivery.edges.items():
        if edge['consumer'] != cid:
            continue
        if consumer_contributions is not None and not edge['consumers'] & set(consumer_contributions):
            continue
        state = implementation_state(delivery, eid, assessments, target)
        if state['state'] == 'unknown':
            unknown.append(eid)
        elif state['state'] == 'unsatisfied':
            unavailable.append(eid)
        states.append(state)
    if unknown:
        raise CheckError('availability.unknown', 'due implementation conditions lack a known current assessment; planning-only does not hide unknowns', refs=states, owner='engineering-owner')
    if payload['mode'] == 'planning-only':
        exception = payload['planning_exception']
        if exception is None or set(exception['unmet_implementation_edges']) != set(unavailable):
            raise CheckError('dispatch.planning-edge', 'planning exception must name exactly the known unmet implementation conditions', refs=states)
    elif unavailable:
        raise CheckError('availability.unavailable', 'required provider contribution is not currently available', refs=states, owner='engineering-owner')
    return states
