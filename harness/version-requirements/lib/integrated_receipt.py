"""Replay a retained current G3/integrated result; never trust a saved PASS.

The input/result are ordinary evidence references, not another completion
database. Memoization is confined to one immutable GitStore invocation and
restores all reads into the caller's audit/retention closure.
"""
import copy
import json

from .core import canonical_bytes, parse_json
from .errors import CheckError
from .models import validate
from .reviews import evidence
from .ui_receipts import compare as compare_ui, historical, locations


def semantic_facts(value):
    """Display prose is not a fact identity; preserve every other field."""
    if isinstance(value, dict):
        return {key: semantic_facts(item) for key, item in value.items() if key != 'scope'}
    if isinstance(value, list):
        return [semantic_facts(item) for item in value]
    return value


def read_integrated_receipt(context, context_ref, result_ref, *, allow_alternatives=False):
    from .integrated import check_integrated

    store = context.store
    key = canonical_bytes([context.version['version'], context.version['delivery_line'], context_ref, result_ref, allow_alternatives, locations(getattr(context, 'snapshot', {}))])
    cache = store._integrated_receipts
    if key in cache:
        result, inputs = cache[key]
        store.inputs.update(inputs)
        return copy.deepcopy(result)
    with store.input_scope():
        origin = validate('snapshot', parse_json(evidence(store, context_ref)))
        family = origin['subject'].split(':', 1)[0]
        check = check_integrated
        if family != 'change':
            if not allow_alternatives or family not in ('scope', 'task', 'pr'):
                raise CheckError('integrated-receipt.path-kind', 'this consumer requires an actual Standard Change integration')
            from .scope_delivery import check_scope_delivery
            from .tiny_delivery import check_tiny_integrated
            check = check_scope_delivery if family == 'scope' else check_tiny_integrated
        if ((origin['gate'], origin['phase'], origin['evaluation_mode']) != ('G3', 'integrated', 'current') or
                (origin['version'], origin['delivery_line']) != (context.version['version'], context.version['delivery_line']) or
                'slot_release_ref' in origin):
            raise CheckError('integrated-receipt.origin', 'retain the original current integration check before slot-release confirmation')
        for ref in (context_ref, result_ref):
            if not ref['path'].startswith(context.vr + '/trace/evidence/') or not store.ancestor(origin['head_revision'], ref['commit']):
                raise CheckError('integrated-receipt.path', 'retain original integrated input/output after their checked metadata head in this Version evidence namespace')
        output = parse_json(evidence(store, result_ref))
        keys = ('gate', 'phase', 'subject', 'evaluation_mode', 'version', 'delivery_line',
                'metadata_revision', 'head_revision', 'target_revision', 'control_revision')
        expected = {key: origin[key] for key in keys}
        expected.update(baseline=origin['baseline_ref'], result='passed', exit_code=0)
        if not isinstance(output, dict) or any(output.get(key) != value for key, value in expected.items()):
            raise CheckError('integrated-receipt.result', 'retained integration output must match its actual current input and successful exit')
        rows = output.get('diagnostics')
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or
                rows[0].get('rule_id') != 'G3.integrated' or rows[0].get('result') != 'passed' or
                not isinstance(rows[0].get('evidence'), dict) or
                (family != 'scope' and rows[0]['evidence'].get('current_integration') is not True)):
            raise CheckError('integrated-receipt.result', 'historical output or an unverified PASS label is not original current integration')
        # Keep receipt reads out of the nested original decision's retained
        # input calculation, exactly as for the original pre-merge replay.
        with store.input_scope():
            replay = check(store, historical(origin, getattr(context, 'snapshot', {})))['evidence']
        replay = parse_json(json.dumps(replay, ensure_ascii=False, allow_nan=False))
        reported = copy.deepcopy(rows[0]['evidence'])
        compare_ui(context, reported.get('ui'), replay.get('ui'))
        if 'ui' in replay:
            reported['ui'] = replay['ui']
        if 'current_integration' in reported:
            reported['current_integration'] = replay['current_integration']
        if canonical_bytes(semantic_facts(reported)) != canonical_bytes(semantic_facts(replay)):
            raise CheckError('integrated-receipt.replay', 'saved integrated facts differ from full original Gate recomputation')
        result = {'context_ref': context_ref, 'result_ref': result_ref, 'snapshot': origin, 'evidence': replay}
        reads = dict(store.inputs)
    cache[key] = (copy.deepcopy(result), reads)
    return result
