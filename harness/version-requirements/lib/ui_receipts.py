"""Compare retained UI observations with a fresh fixed-time recomputation.

This validates the saved receipt envelope; package/decision rules and every
live query remain exclusively in the shared UI checker. It never grants a
current permission or consults a remote during historical replay.
"""
from copy import deepcopy

from .core import canonical_bytes
from .errors import CheckError
from .verification import _time


def locations(snapshot):
    """Only explicit physical recovery locators, never authority/permission."""
    if not snapshot or 'ui' not in snapshot:
        return {}
    return {'ui': {key: deepcopy(snapshot['ui'].get(key, {} if key == 'repositories' else []))
                   for key in ('repositories', 'external_files')}}


def relocate(original, current):
    """Relocate fixed Git/media objects; preserve every fixed business input."""
    selected = deepcopy(original)
    if 'ui' in selected and 'ui' in current:
        available = current['ui']['repositories']
        selected['ui']['repositories'] = {key: available.get(key, path)
            for key, path in selected['ui']['repositories'].items()}
        def identity(row):
            return row['uri'], row['version'], row['sha256']
        for row in selected['ui']['external_files']:
            matches = [item for item in current['ui'].get('external_files', []) if identity(item) == identity(row)]
            if len(matches) > 1:
                raise CheckError('ui.recovery-ambiguous', 'one fixed external object has multiple recovery paths')
            if matches:
                row['path'] = matches[0]['path']
    return selected


def historical(original, current):
    selected = relocate(original, current)
    selected['evaluation_mode'] = 'historical'
    return selected


def _fixed_identity(value):
    result = deepcopy(value)
    result['mode'] = 'historical'
    # Absolute installation location is a display locator. All code, schema,
    # dependency and capability hashes are still compared without alteration.
    if 'implementation' in result:
        result['implementation']['invoked_entry'] = '<validated installation>'
    return result


def _envelope(value):
    result = deepcopy(value)
    result.pop('result', None)
    snapshot = result['snapshot']
    snapshot['mode'] = 'historical'
    snapshot['repositories'] = {key: '<restored fixed objects>' for key in snapshot['repositories']}
    for row in snapshot['external_files']:
        row['path'] = '<restored fixed media>'
    return result


def compare(context, reported, replay):
    """Require the original current UI observation and identical fixed facts."""
    if reported is None and replay is None:
        return
    if not isinstance(reported, dict) or not isinstance(replay, dict):
        raise CheckError('ui.receipt-missing', 'retained delivery must include its complete required UI evidence')
    try:
        actual, fixed = reported['result'], reported['result']['fixed_result']
        if (reported['snapshot']['mode'] != 'current' or replay['snapshot']['mode'] != 'historical' or
                actual['mode'] != 'current' or actual['result'] != 'PASS' or fixed['result'] != 'PASS' or
                replay['result']['result'] != 'PASS' or actual['diagnostics'] or
                actual['engineering_authorized'] is not False or actual['current_permission'] is not False or
                actual['action'] != reported['snapshot']['action'] or
                actual['policy_ref'] != reported['snapshot']['policy_ref']):
            raise ValueError('not an original successful current UI observation')
        if canonical_bytes(_envelope(reported)) != canonical_bytes(_envelope(replay)):
            raise ValueError('fixed UI envelope, selections or execution bindings differ')
        if canonical_bytes(_fixed_identity(fixed)) != canonical_bytes(_fixed_identity(replay['result'])):
            raise ValueError('fixed UI result differs from full recomputation')
        for key in fixed:
            if key not in ('mode', 'proof_scope') and actual.get(key) != fixed[key]:
                raise ValueError('outer UI result relabels a fixed fact: ' + key)
        if fixed['ui_required'] is False:
            if (actual.get('ui_applicability') != 'not-applicable' or actual['current_checked'] is not False or
                    actual['observations']):
                raise ValueError('non-UI applicability is not the validated empty-observation case')
            return
        if actual['current_checked'] is not True or not actual['observations']:
            raise ValueError('required UI has no successful original authority observation')
        from ui_design.models import parse, validate
        reference = replay['snapshot']['policy_ref']
        policy = validate('policy', parse(context.store.read(reference['commit'], reference['path'], reference['sha256']), reference['path']), 'policy')
        selected = replay['snapshot']['authorities']
        expected = {}
        for authority in policy['authorities']:
            chosen = [row for row in selected if row['repository'] == authority['repository']]
            if len(chosen) != 1:
                raise ValueError('replayed authority denominator is incomplete')
            expected.setdefault((authority['remote'], authority['ref']), []).extend(chosen)
        observed = set()
        for row in actual['observations']:
            key = (row['remote'], row['ref'])
            if key not in expected or key in observed:
                raise ValueError('unexpected or duplicate original authority observation')
            observed.add(key)
            if (sorted(map(canonical_bytes, row['selections'])) != sorted(map(canonical_bytes, expected[key])) or
                    row['exit_code'] != 0 or any(item['commit'] != row['actual_commit'] for item in expected[key]) or
                    row['stdout'].splitlines() != [row['actual_commit'] + '\t' + row['ref']] or
                    _time(row['finished_at']) < _time(row['started_at'])):
                raise ValueError('original authority query does not substantiate its selected fixed revision')
        if observed != expected.keys():
            raise ValueError('original authority observations omit a required endpoint')
    except (KeyError, TypeError, ValueError) as error:
        raise CheckError('ui.receipt-replay', str(error)) from error
