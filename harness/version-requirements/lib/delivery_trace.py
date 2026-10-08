"""Actual Task/implementation/execution associations in the existing Change Trace.

This read-only slice checks local contribution evidence. It does not establish
G3, semantic acceptance, a due integration condition, or permission to archive.
"""
from collections import defaultdict

from .control import event
from .core import canonical_bytes
from .errors import CheckError
from .models import unique, validate
from .openspec_artifacts import task_evidence, tasks
from .planning_trace import check_links
from .verification import check_execution


def current_ref(store, reference, revision):
    """Preserve the original reference while comparing actual bytes and mode."""
    data = store.ref(reference)
    store.read(revision, reference['path'], reference['sha256'])
    if store.tree(reference['commit'])[reference['path']] != store.tree(revision)[reference['path']]:
        raise CheckError('delivery-trace.file-mode', 'referenced input changed file mode', refs=[reference])
    return data


def tiny_review_key(subject):
    """A filesystem-safe key for the real task/PR identity, not a candidate ID."""
    from urllib.parse import quote
    validate('tiny_subject', subject)
    kind, identity = subject.split(':', 1)
    return kind + '-' + quote(identity, safe='-_.')


def metadata_scope(context, candidate_id, control=None, *, delivery_subject=None):
    """Known delivery evidence locations; published control needs actual input."""
    store = context.store
    if delivery_subject is None:
        metadata = {context.vr + '/trace/changes/' + candidate_id + '.yaml',
                    context.vr + '/reviews/delivery/' + candidate_id + '.yaml',
                    context.vr + '/reviews/merge/' + candidate_id + '.yaml',
                    context.vr + '/reviews/integration/' + candidate_id + '.yaml'}
    else:
        if candidate_id is not None:
            raise CheckError('tiny.owner', 'a task/PR cannot impersonate a candidate')
        key = tiny_review_key(delivery_subject)
        metadata = {context.vr + '/reviews/' + phase + '/' + key + '.yaml'
                    for phase in ('merge', 'integration')}
    evidence_roots = (context.vr + '/trace/evidence/', context.vr + '/trace/verification/')
    if control is not None:
        # Only a Gate's already parsed, published control chain may classify
        # these files as control metadata. A folder name or unconfirmed draft
        # is not sufficient, and explicit executed inputs remain protected.
        for reference in control.event_refs.values():
            row = event(store, reference)
            if (row['version'], row['target_line']) == (context.version['version'], context.version['delivery_line']):
                metadata.add(reference['path'])
    return metadata, evidence_roots


def tested_content(context, executions, head_revision, task_path, *, candidate_id, control=None, integration=None, delivery_subject=None):
    """Allow evidence saves, never silently promote changed code or declared inputs."""
    store = context.store
    metadata, evidence_roots = metadata_scope(context, candidate_id, control, delivery_subject=delivery_subject)
    for execution in executions:
        record = execution['record']
        refs = [execution['reference'], record['execution_ref']]
        if record['kind'] == 'automatic':
            refs.append(record['automatic']['report_ref'])
        else:
            refs.append(record['manual']['acceptance']['evidence_ref'])
            refs.extend(row['evidence_ref'] for row in record['manual']['observations'])
        for reference in refs:
            current_ref(store, reference, head_revision)
    actual = integration['facts']['target_revision'] if integration else head_revision
    reviewed = {ref['path'] for ref in integration['engineering_inputs'].values()} if integration else set()
    head = store.tree(actual)
    for execution in executions:
        record = execution['record']
        tested = record['tested_revision']
        if integration:
            facts = integration['facts']
            original = store.ancestor(tested, facts['source_revision'])
            fresh = store.ancestor(facts['merged_revision'], tested) and store.ancestor(tested, head_revision)
            if not (original or fresh):
                raise CheckError('delivery-trace.tested-history', 'integrated evidence must test the admitted source or actual integrated history')
        elif not store.ancestor(tested, head_revision):
            raise CheckError('delivery-trace.tested-history', 'pre-archive evidence must come from this feature history, not another branch')
        for reference in [*record['input_refs'], *record['identities'].values()]:
            current_ref(store, reference, actual)
        before = store.tree(tested)
        changed = []
        for path in sorted(before.keys() | head.keys()):
            if before.get(path) == head.get(path):
                continue
            if path in metadata or path in reviewed or path.startswith(evidence_roots):
                continue
            if path == task_path and path in before and path in head and before[path][:2] == head[path][:2]:
                if tasks(store.read(tested, path))[1] == tasks(store.read(actual, path))[1]:
                    continue
            changed.append(path)
        if changed:
            raise CheckError('delivery-trace.stale-execution', 'engineering content changed after the selected execution; run the applicable checks again',
                             refs=[{'tested_revision': tested, 'head_revision': head_revision, 'target_revision': actual, 'changed_paths': changed}])


def coverage_identity(delivery, row):
    """Coverage selects the exact current allocation, including historical R pins."""
    contribution = row['contribution']
    if 'requirement' in row:
        allocation = delivery.allocations.get(contribution)
        if allocation is None:
            raise CheckError('delivery-trace.contribution', 'execution coverage names an absent business allocation', refs=[contribution])
        info = allocation['info']
        if ((row['requirement'], row['revision'], row['record_ref'], row['configuration_ref']) !=
                (info['uid'], info['value']['revision'], info['record_ref'], info['configuration_ref']) or
                not set(row['acceptance']) <= allocation['acceptance']):
            raise CheckError('delivery-trace.coverage-identity', 'execution coverage differs from the current fixed R/configuration/AC allocation', refs=[row])
    else:
        capability = delivery.capabilities.get(contribution)
        if capability is None or capability['capability'] != row['capability']:
            raise CheckError('delivery-trace.capability', 'execution coverage names an absent or different technical capability', refs=[row])


def check_delivery_trace(delivery, trace, observation, *, head_revision, verification_inputs, control=None, integration=None):
    """Read local delivery associations against separately supplied E expectations.

    The caller must already resolve the applicable BL/current map, actual CLI
    observation, control and planning approval. G3 additionally binds delivery
    Review and due conditions; an actual action request is still separate.
    """
    validate('planning_trace', trace)
    validate('delivery_verification_inputs', verification_inputs)
    content = trace.get('delivery')
    if content is None:
        raise CheckError('delivery-trace.required', 'this Change has no actual Task/implementation/execution associations yet')
    if content.get('integration_observation_ref') is not None:
        raise CheckError('delivery-trace.integration-required', 'integration must be verified before projecting the actual archived associations')
    if content.get('archive_observation_ref') is not None:
        raise CheckError('delivery-trace.archive-required', 'archived delivery requires verified file relocation before checking its associations')
    cid, context, store = trace['candidate_id'], delivery.context, delivery.store
    if (trace['version'], trace['delivery_line']) != (context.version['version'], context.version['delivery_line']):
        raise CheckError('delivery-trace.owner', 'delivery Trace belongs to a different Version/line')
    if cid not in delivery.active or trace['change'] != delivery.candidates[cid]['change_name']:
        raise CheckError('delivery-trace.candidate', 'delivery Trace must name this active candidate and its actual Change')
    check_links(delivery, trace, observation, head_revision)
    task_ref = content['task_ref']
    if observation['artifacts']['tasks'] != [task_ref['path']]:
        raise CheckError('delivery-trace.task-location', 'delivery Task reference does not select the actual CLI Task artifact')
    raw = store.ref(task_ref)
    fixed_tasks, normalized = tasks(raw)
    current_raw = store.read(head_revision, task_ref['path'])
    actual_tasks, actual_normalized = tasks(current_raw)
    task_evidence(raw, store=store)
    task_evidence(current_raw, store=store)
    if (fixed_tasks != actual_tasks or normalized != actual_normalized or
            actual_tasks != observation['tasks'] or
            store.tree(task_ref['commit'])[task_ref['path']][:2] != store.tree(head_revision)[task_ref['path']][:2]):
        raise CheckError('delivery-trace.task-stale', 'delivery Task reference or supplied observation differs from actual Task meaning/state')
    if not actual_tasks or not all(row['done'] for row in actual_tasks.values()):
        raise CheckError('delivery-trace.tasks-incomplete', 'actual Tasks are not complete; links cannot stand in for their state')
    implementations = unique(content['implementations'], 'task_id', location='delivery Trace')
    if implementations.keys() != actual_tasks.keys():
        raise CheckError('delivery-trace.task-coverage', 'each actual Task needs implementation references; do not invent or omit Task IDs')
    planning = {path for paths in observation['artifacts'].values() for path in paths}
    selected = {canonical_bytes(row['verification_ref']) for row in content['verification']}
    for row in implementations.values():
        for reference in row['file_refs']:
            # A verification-only Task may reference its actual selected E.
            # Do not require a made-up code edit for every OpenSpec Task. The E
            # is checked below; Review still decides its relevance to this Task.
            selected_execution = canonical_bytes(reference) in selected
            if reference['path'] in planning or (reference['path'].startswith('requirements/') and not selected_execution):
                raise CheckError('delivery-trace.implementation-role', 'Task output must be an engineering file or its selected actual E, not upstream requirements or planning metadata')
            current_ref(store, reference, head_revision)
    expectations = {}
    for item in verification_inputs:
        key = canonical_bytes(item['verification_ref'])
        if key in expectations:
            raise CheckError('delivery-trace.execution-duplicate', 'one fixed E has more than one expected execution context')
        expectations[key] = item
    if selected != expectations.keys():
        raise CheckError('delivery-trace.execution-context', 'selected E references must exactly match independently supplied execution expectations')
    executions = {}
    for key, item in expectations.items():
        execution = check_execution(context, item['verification_ref'], tested_revision=item['tested_revision'], identities=item['identities'], engineering_review=delivery.review)
        for row in execution['record']['coverage']:
            coverage_identity(delivery, row)
        executions[key] = execution
    tested_content(context, list(executions.values()), head_revision, task_ref['path'], candidate_id=cid, control=control, integration=integration)
    obligations = {row['id']: row for row in delivery.plan['obligations']}
    authorized = defaultdict(set)
    for link in trace['links']:
        for oid in link['verification_obligations']:
            authorized[oid].add(link['contribution'])
    covered, capabilities, pairs, links = defaultdict(set), set(), set(), []
    for row in content['verification']:
        oid = row['obligation_id']
        key = canonical_bytes(row['verification_ref'])
        pair = (oid, key)
        if pair in pairs:
            raise CheckError('delivery-trace.verification-duplicate', 'one obligation/E association must consolidate its selected case IDs')
        pairs.add(pair)
        obligation = obligations.get(oid)
        if obligation is None or oid not in authorized:
            raise CheckError('delivery-trace.verification-obligation', 'delivery association must select this Trace\'s actual planning responsibility')
        execution = executions[key]
        case_ids = set(row['case_ids'])
        if not case_ids <= execution['cases'].keys():
            raise CheckError('delivery-trace.test-case', 'delivery association names an absent executed case ID')
        used_cases, local = set(), set()
        for coverage in execution['record']['coverage']:
            contribution = coverage['contribution']
            if contribution not in authorized[oid] or not set(coverage['case_ids']) <= case_ids:
                continue
            if 'capability_ref' in obligation:
                if coverage.get('capability') is None or contribution != obligation['capability_ref']:
                    continue
                capabilities.add(contribution)
            else:
                if ((coverage.get('requirement'), coverage.get('revision')) != (obligation['requirement'], obligation['revision']) or
                        contribution not in obligation['contributions']):
                    continue
                acs = set(coverage['acceptance']) & set(obligation['acceptance'])
                if not acs:
                    continue
                covered[contribution].update(acs)
            local.add(contribution)
            used_cases.update(coverage['case_ids'])
        if used_cases != case_ids:
            raise CheckError('delivery-trace.test-coverage', 'selected cases do not substantiate the declared local contribution responsibility')
        links.append({**row, 'contributions': sorted(local), 'checkpoint': obligation['checkpoint']})
    for link in trace['links']:
        contribution = link['contribution']
        if ((link['acceptance'] and not set(link['acceptance']) <= covered[contribution]) or
                (not link['acceptance'] and contribution not in capabilities)):
            raise CheckError('delivery-trace.local-coverage', 'actual selected executions do not cover every local AC/capability association', refs=[contribution])
    return {'task_ref': task_ref, 'implementations': content['implementations'], 'verification_links': links,
            'local_acceptance': {key: sorted(value) for key, value in sorted(covered.items())},
            'local_capabilities': sorted(capabilities),
            'scope': 'local Task/implementation/execution references only; no G3, semantic acceptance, full obligation completion, dependency availability or archive permission'}
