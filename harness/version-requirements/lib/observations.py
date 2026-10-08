"""Fixed report inputs and diagnostics; no new authoritative state or action."""
from dataclasses import replace

from .context import resolve
from .control import event
from .control_delivery import read_delivery_control
from .core import canonical_bytes, digest
from .delivery import DeliveryIndex
from .dispatch import baseline_context, current_engineering, preserved_inputs
from .errors import CheckError, InputError
from .feasibility import check_feasibility
from .requirements import RequirementIndex
from .review_scope import ReviewScope
from .runtime import implementation_manifest


def diagnostic_state(error):
    if error.rule in ('G4.execution-identity', 'G4.execution-environment', 'G4.input-revision', 'ref.digest'):
        return 'stale'
    if any(part in error.rule for part in ('stale', 'mismatch', 'history', 'candidate-context')):
        return 'stale'
    return 'unknown' if error.unreadable else 'unsatisfied'


def observe(checks, name, action):
    try:
        value = action()
        checks.append({'check': name, 'state': 'satisfied'})
        return value
    except CheckError as error:
        checks.append({'check': name, 'state': diagnostic_state(error), 'diagnostic': error.diagnostic()})
        return None


def load(context):
    """Reuse the selected phase's explicit engineering inputs, never latest files.

    Draft reports can expose gaps before a BL exists. Downstream reports still
    qualify the fixed BL and current engineering Review; a failed check remains
    visible and prevents a ready recommendation, rather than hiding all rows.
    """
    checks, baseline, current = [], context, context
    snapshot, store = context.snapshot, context.store
    selected = snapshot.get('engineering_inputs')
    if snapshot.get('dispatch_ref'):
        payload = event(store, snapshot['dispatch_ref'])['payload']
        selected = {key: payload[key] for key in ('map_ref', 'verification_plan_ref', 'engineering_review_ref')}
    if context.baseline is not None:
        result = observe(checks, 'effective-baseline', lambda: baseline_context(store, snapshot))
        # Retain the exact product denominator even when its effective/current
        # qualification fails. Such a view has diagnostics, never ready entries.
        baseline = replace(context)
        if result is not None:
            baseline, checked = result
            if selected:
                current_result = observe(checks, 'current-engineering', lambda: current_engineering(
                    baseline, snapshot, selected, executing=True))
                if current_result is not None:
                    current = current_result
                observe(checks, 'preserved-product-inputs', lambda: preserved_inputs(baseline, snapshot['metadata_revision'], checked))
        if selected:
            current = replace(current.at(selected['engineering_review_ref']['commit'], snapshot['version']),
                              snapshot=snapshot)
        elif snapshot['gate'] != 'G1':
            raise InputError('report.engineering-inputs', 'downstream observation requires the phase\'s explicit map, plan and engineering Review')
    elif (snapshot['gate'], snapshot['phase']) != ('G1', 'content'):
        raise InputError('report.snapshot', 'observation requires G1/content or a fixed baseline phase snapshot')
    requirements = RequirementIndex(baseline)
    observe(checks, 'content', requirements.check_content)
    delivery = DeliveryIndex(requirements, engineering_context=current,
                             map_ref=selected['map_ref'] if selected else None,
                             verification_plan_ref=selected['verification_plan_ref'] if selected else None)
    structure = observe(checks, 'delivery-structure', delivery.check)
    scope = ReviewScope(requirements, delivery)
    if structure is not None:
        observe(checks, 'feasibility', lambda: check_feasibility(delivery))
        observe(checks, 'engineering-review', scope.check_engineering)
    control = (observe(checks, 'control', lambda: read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot))
               if snapshot['control_revision'] else None)
    return requirements, delivery, scope.engineering_questions, control, checks


def generated_from(context, *, filters=None):
    # Re-observe authority after the complete read. An intervening target or
    # control move cannot leave a report labelled current.
    resolve(context.store, context.snapshot)
    inputs = {'snapshot': context.snapshot, 'filters': filters or {},
              'resolved_inputs': context.store.manifest(), 'generator_manifest': implementation_manifest()}
    return {**inputs, 'sha256': digest(canonical_bytes(inputs))}
