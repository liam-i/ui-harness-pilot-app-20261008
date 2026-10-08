"""G2 dispatch preflight: fixed BL plus current engineering and control.

Existing/external providers require actual current execution evidence. Candidate
providers replay their actual same-target integrated Trace. A draft grants no
permission; confirmed publication may continue its explicit Propose request.
Neither path publishes a reservation or authorizes Apply.
"""
from dataclasses import replace

from .availability import implementation_dependencies
from .baselines import check_baseline, published_chain
from .context import resolve
from .control import ALLOCATIONS, INDEX, event
from .control_delivery import KINDS, read_delivery_control
from .core import digest, parse_yaml
from .delivery import DeliveryIndex
from .errors import CheckError, InputError
from .feasibility import check_feasibility
from .handoff import reference_handoff
from .models import validate
from .requirements import RequirementIndex
from .review_scope import References, ReviewScope
from .runtime import reviewed_implementation

CONFIG = 'harness/version-requirements/config/project.yaml'


def same_engineering(store, left, right, *, planning_files=(), metadata_files=()):
    """Metadata can advance before Propose; business/code/Spec inputs cannot."""
    before, after = store.tree(left), store.tree(right)
    def metadata(path):
        return (path.startswith('requirements/') or path.startswith('harness/version-requirements/') or
                path == 'scripts/requirements-check' or path in metadata_files)
    changed = sorted(path for path in before.keys() | after.keys()
                     if not metadata(path) and path not in planning_files and before.get(path) != after.get(path))
    if changed:
        raise CheckError('dispatch.engineering-changed', 'dispatch metadata/head contains unreviewed engineering changes beyond the selected target', refs=changed)


def baseline_snapshot(store, snapshot):
    """Select G1's original B/C without changing or evaluating the snapshot."""
    reference = snapshot['baseline_ref']
    if reference is None:
        raise CheckError('snapshot.baseline-required', 'dispatch requires a fixed effective baseline')
    baseline = validate('baseline', parse_yaml(store.ref(reference)))
    selected = {**snapshot, 'gate': 'G1', 'phase': 'effective', 'subject': 'baseline:' + baseline['id'],
                'metadata_revision': reference['commit'], 'head_revision': baseline['content_commit']}
    selected.pop('dispatch_ref', None)
    selected.pop('trace_ref', None)
    selected.pop('apply_request_ref', None)
    selected.pop('apply_origin_ref', None)
    selected.pop('planning_inputs_ref', None)
    selected.pop('verification_inputs', None)
    selected.pop('engineering_inputs', None)
    selected.pop('integration_checks_ref', None)
    selected.pop('slot_release_ref', None)
    for key in ('pre_archive_context_ref', 'final_checks_ref', 'merge_request_ref', 'tiny_ref', 'integration_observation_ref'):
        selected.pop(key, None)
    for key in ('release_candidate_ref', 'release_decision_ref', 'release_observation_ref'):
        selected.pop(key, None)
    return selected


def baseline_context(store, snapshot):
    """G1 receives its original B/C, never the later engineering metadata D."""
    reference = snapshot['baseline_ref']
    selected = baseline_snapshot(store, snapshot)
    context = resolve(store, selected)
    checked = check_baseline(context)
    _, head = published_chain(context, snapshot['target_revision'])
    if head != reference['path']:
        raise CheckError('dispatch.stale-baseline', 'dispatch must select the current effective baseline head of this Version')
    return replace(context), checked


def current_engineering(context, snapshot, payload, *, planning_files=(), executing=False):
    store, version = context.store, context.version['version']
    selected = context.at(payload['engineering_review_ref']['commit'], version)
    selected = replace(selected, snapshot=snapshot,
                       configuration=validate('project_config', store.yaml(selected.content_commit, CONFIG)))
    # A later metadata save cannot silently select another map, owner or rule
    # installation than the engineering Review being used for this admission.
    for revision in {snapshot['metadata_revision'], snapshot['head_revision'], selected.content_commit}:
        if (validate('version', store.yaml(revision, context.vr + '/version.yaml')) != context.version or
                validate('project_config', store.yaml(revision, CONFIG)) != context.configuration):
            raise CheckError('delivery.engineering-context', 'current engineering owner/line/authority differs from the selected BL')
    current = replace(selected, content_commit=snapshot['metadata_revision'])
    installation = reviewed_implementation(current)
    reviewed_implementation(replace(selected, content_commit=snapshot['head_revision']))
    for key in ('map_ref', 'verification_plan_ref', 'engineering_review_ref'):
        ref = payload[key]
        store.read(snapshot['metadata_revision'], ref['path'], ref['sha256'])
        store.read(snapshot['head_revision'], ref['path'], ref['sha256'])
    from .ui_metadata import reviewed_metadata
    installation.update(reviewed_metadata(selected, snapshot, selected.read('reviews/engineering.yaml', 'review')))
    prefix = context.vr + '/questions/'
    questions = lambda revision: {p: v for p, v in store.tree(revision).items() if p.startswith(prefix)}
    if any(questions(revision) != questions(selected.content_commit)
           for revision in (snapshot['metadata_revision'], snapshot['head_revision'])):
        raise CheckError('dispatch.question-review-stale', 'current question set differs from the selected engineering Review context')
    # Only the Apply consumer with a revalidated original admission may allow
    # implementation changes. Product/config/map/Review checks above and below
    # remain mandatory; semantic scope and execution evidence are reviewed at G3.
    if not executing:
        same_engineering(store, snapshot['target_revision'], snapshot['head_revision'], planning_files=planning_files, metadata_files=installation)
    same_engineering(store, snapshot['head_revision'], snapshot['metadata_revision'], metadata_files=installation)
    return selected


def preserved_inputs(context, metadata, checked):
    """The current admission cannot hide edits to its fixed product obligations."""
    source_tree = context.store.tree(context.content_commit)
    prefix = context.vr + '/'
    def protected(path):
        return (path.startswith('requirements/items/') or path.startswith(prefix + 'source/') or
                path.startswith(prefix + 'derived-assets/') or
                path in {prefix + name for name in ('version.yaml', 'scope.yaml', 'reviews/intake.yaml', 'reviews/global.yaml')} or
                path.startswith(prefix + 'reviews/batches/'))
    for ref in checked['evidence']['content']['content_manifest']:
        path = ref['path']
        if protected(path) and path in source_tree and digest(context.store.read(context.content_commit, path)) == ref['sha256']:
            context.store.read(metadata, path, ref['sha256'])


def initial_candidate(store, snapshot, payload, delivery, questions, *, alignment_only=False):
    cid = payload['candidate_id']
    if delivery.candidates[cid]['change_name'] is not None:
        raise CheckError('dispatch.already-proposed', 'bound Change requires planning/resume, not initial dispatch')
    trace = delivery.context.vr + '/trace/changes/' + cid + '.yaml'
    for revision in {snapshot['metadata_revision'], snapshot['head_revision'], snapshot['target_revision']}:
        if store.git('log', '-1', '--format=%H', revision, '--', trace).strip():
            raise CheckError('dispatch.already-proposed', 'candidate has current or deleted Trace history; use its actual delivery stage', refs=[trace])
    states = [] if alignment_only else implementation_dependencies(delivery, cid, payload, snapshot['target_revision'])
    questions.check_endpoints(delivery.requirements.sources.units, delivery.requirements.question_requirement_ids(), candidates=delivery.candidates)
    questions.check_baseline(delivery.requirements.records)
    for qid, group in questions.impacts.items():
        if cid in group['blocking_for']:
            questions.require_resolved(qid)
    return states


def retain_inputs(context, snapshots):
    store, config = context.store, context.configuration
    # Control history is retained by its append-only branch. All other reads
    # contributing to this decision require exact authority pins.
    control_history = set(store.git('rev-list', context.snapshot['control_revision']).decode().splitlines())
    commits = {r['commit'] for r in store.manifest()
               if not (r['path'] in (INDEX, ALLOCATIONS) and r['commit'] in control_history)}
    commits.update(snapshots)
    names = [config['pin_namespace'] + commit for commit in sorted(commits)]
    actual = {}
    for start in range(0, len(names), 100):
        actual.update(store.remote_refs(config['authority_remote'], names[start:start + 100]))
    for commit in commits:
        if actual.get(config['pin_namespace'] + commit) != commit:
            raise CheckError('dispatch.retention', 'fixed admission input lacks its exact authority pin', refs=[commit])
    return names


def check_dispatch(store, snapshot, *, alignment_only=False):
    reference = snapshot.get('dispatch_ref')
    if reference is None or snapshot['control_revision'] is None:
        raise CheckError('dispatch.context-required', 'dispatch requires its exact saved event and control predecessor')
    if reference['commit'] != snapshot['metadata_revision']:
        raise InputError('dispatch.metadata', 'dispatch preflight metadata must be the saved draft event commit')
    row = event(store, reference)
    if row['kind'] not in KINDS:
        raise InputError('dispatch.initial-only', 'unproposed candidate requires dispatch or its original reservation alignment')
    payload = validate(KINDS[row['kind']], row['payload'])
    if (row['version'] != snapshot['version'] or row['target_line'] != snapshot['delivery_line'] or
            snapshot['subject'] != 'candidate:' + snapshot['version'] + '/' + payload['candidate_id'] or
            payload['baseline_ref'] != snapshot['baseline_ref'] or payload['target_revision'] != snapshot['target_revision']):
        raise InputError('dispatch.snapshot-binding', 'event, typed candidate, baseline and target must select one exact admission')
    context, checked = baseline_context(store, snapshot)
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    key = (snapshot['delivery_line'], snapshot['version'], payload['candidate_id'])
    reservation = control.reservations.get(key)
    published = control.event_refs.get(reference['event_id']) == reference
    if published:
        if reservation is None or reservation['event_ref'] != reference:
            raise CheckError('dispatch.stale-reservation', 'resume the exact latest published event of the reservation')
        if not alignment_only:
            control.holds.require_clear(line=key[0], entry='propose', subjects=reservation['inputs']['subjects'])
        preview = {'scope': 'confirmed published reservation; current Gate still rechecks all admission inputs',
                   'control_revision': control.revision, 'event_ref': reference,
                   'reservation_ref': reservation['reservation_ref'], 'mode': payload['mode']}
    else:
        preview = control.preview(store, reference, alignment_only=alignment_only)
    current = current_engineering(context, snapshot, payload)
    for revision in {snapshot['metadata_revision'], snapshot['head_revision'], current.content_commit}:
        preserved_inputs(context, revision, checked)
    requirements = RequirementIndex(context)
    requirements.check_content()
    delivery = DeliveryIndex(requirements, engineering_context=current, map_ref=payload['map_ref'],
                             verification_plan_ref=payload['verification_plan_ref'])
    structure = delivery.check()
    feasible = check_feasibility(delivery)
    review_scope = ReviewScope(requirements, delivery)
    review = review_scope.check_engineering()
    states = initial_candidate(store, snapshot, payload, delivery, review_scope.engineering_questions,
                               alignment_only=alignment_only)
    from .ui_integration import candidate
    ui = candidate(delivery, snapshot, payload['candidate_id'], action='propose')
    # Include explicit/extra Review and event evidence in the retained closure.
    refs = References(current)
    refs.fixed(payload)
    refs.fixed(row)
    refs.fixed(review)
    for ref in review['reviewed_inputs'] + review['context_refs']:
        refs.add(ref)
    handoff = reference_handoff(delivery, payload, snapshot, ui=ui) if published and not alignment_only else None
    pins = retain_inputs(context, [snapshot[k] for k in ('metadata_revision', 'head_revision', 'target_revision')])
    # Recheck actual authority after resolving the complete fixed input set.
    # This remains an observation, not a lease on future publication.
    resolve(store, context.snapshot)
    return {'rule_id': 'rc.dispatch-alignment' if alignment_only else 'G2.dispatch', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'baseline_ref': snapshot['baseline_ref'], 'publication_commit': checked['evidence']['publication_commit'],
                'dispatch_ref': reference, 'map_ref': payload['map_ref'], 'engineering_review_ref': payload['engineering_review_ref'],
                'engineering_review': review['id'], 'dependencies': states,
                'questions': [{'id': q['id'], 'status': q['status'], 'blocking_for': q['blocking_for']}
                              for q in review_scope.engineering_questions.values.values()],
                'structure': structure, 'feasibility': feasible, 'ui': ui,
                'capacity': preview, 'retained_pins': pins, 'published': published,
                'propose_permission': published and snapshot['evaluation_mode'] == 'current' and not alignment_only, 'handoff': handoff,
                'scope': ('local RC allocation/Review alignment only; control and dependency readiness still require G2' if alignment_only else
                          'unproposed candidate with checked current provider contributions; draft needs publication, confirmed current release may continue its explicit Propose request; no Apply permission')},
            'next_owner': 'coding-agent' if published and snapshot['evaluation_mode'] == 'current' else 'integrator'}
