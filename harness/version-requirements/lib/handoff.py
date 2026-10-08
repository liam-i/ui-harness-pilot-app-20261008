"""Rebuild a candidate's reference bundle; no copied requirements or feature plan."""
from .assets import AssetIndex
from .core import canonical_bytes, digest
from .review_scope import References


def reference_handoff(delivery, payload, snapshot, *, ui=None):
    requirements, context = delivery.requirements, delivery.requirements.context
    refs = References(context)
    assets = AssetIndex(context, sources=requirements.sources)
    selected, origins, usages = [], {}, []
    for entry in delivery.candidates[payload['candidate_id']]['allocation']:
        info = requirements.records[entry['requirement']]
        selected.append({'allocation_ref': payload['candidate_id'] + '/' + entry['id'],
                         'requirement': info['uid'], 'revision': info['value']['revision'],
                         'acceptance': entry['acceptance'], 'record_ref': info['record_ref'],
                         'configuration_ref': info['configuration_ref']})
        refs.add(info['record_ref'])
        refs.add(info['configuration_ref'])
        refs.file(context.vr + '/scope.yaml')
        for source in info['value']['source_refs']:
            if not set(source.get('acceptance', info['acs'])) & set(entry['acceptance']):
                continue
            if source['role'] == 'origin':
                identity = source['unit']
                owner = context.at(info['record_ref']['commit'], identity.split('/', 1)[0])
                index = assets._source_index(owner)
                unit = index.units[identity]
                file = index.files[unit['file']]
                locator = {'commit': owner.content_commit, 'path': owner.vr + '/source/units.yaml',
                           'sha256': digest(context.store.read(owner.content_commit, owner.vr + '/source/units.yaml'))}
                key = canonical_bytes([identity, locator])
                origins[key] = {'id': identity, 'units_ref': locator, 'file_ref': file['content_ref'],
                                'selector': unit['selector'], 'fragment_sha256': unit['fragment_sha256']}
                refs.fixed(origins[key])
            else:
                identity = source['decision']
                owner = context.at(info['record_ref']['commit'], identity.split('/', 1)[0])
                questions = requirements.question_index(owner)
                question = questions.resolve(identity)
                refs.file(questions.paths[question['id']], owner.content_commit)
                refs.fixed(question)
        for use in info['value']['asset_refs']:
            if set(use.get('acceptance', info['acs'])) & set(entry['acceptance']):
                resolved = assets.resolve_use(use, owner=requirements.asset_owner(info), acceptance=info['acs'])
                usages.append({'requirement': info['uid'], **resolved})
                refs.fixed(resolved)
    # Derived-input links remain links; their actual owner manifests, outputs,
    # transformation and review references stay in their original locations.
    for value in assets.uses:
        refs.fixed(value)
    for (commit, path), rows in assets._manifests.items():
        refs.file(path, commit)
        refs.fixed(list(rows.values()))
    refs.fixed(payload['context_refs'])
    refs.fixed(delivery.review['engineering'])
    generated = {key: snapshot[key] for key in ('version', 'delivery_line', 'evaluation_mode', 'metadata_revision',
        'head_revision', 'target_revision', 'control_revision', 'baseline_ref', 'dispatch_ref')}
    generated.update(map_ref=payload['map_ref'], verification_plan_ref=payload['verification_plan_ref'],
                     engineering_review_ref=payload['engineering_review_ref'])
    result = {'generated_from': generated, 'candidate_id': payload['candidate_id'], 'mode': payload['mode'],
              'requirements': selected, 'source_units': [origins[key] for key in sorted(origins)],
              'asset_uses': usages, 'input_refs': refs.result(),
              'scope': 'rebuildable reference entry points for the released candidate; source/map/Review remain authoritative; no Feature Tasks or Apply authorization'}
    if ui is not None:
        # The original map consumer and its approved closure remain references.
        # Remote observations are kept in the Gate evidence, not copied Tasks.
        result['ui'] = {key: ui[key] for key in ('inputs_ref', 'policy_ref', 'bindings_ref', 'input_digest')}
        result['ui']['consumers'] = ui['result']['consumers']
        result['ui']['packages'] = ui['result']['packages']
    result['input_digest'] = digest(canonical_bytes(result))
    return result
