"""业务关系解析。只产生受审交付映射的输入，不推断执行顺序或完成状态。"""
from .core import canonical_bytes
from .errors import CheckError
from .models import unique
from .requirements import ac_subset
from .reviews import evidence


def condition(store, entry, *, location):
    when = entry.get('when', 'always')
    if when == 'always':
        return True
    if when is None:
        raise CheckError('dependency.condition-unknown', 'explicit null is unknown, not always/false', refs=[location])
    evidence(store, when['decision_ref'])
    if when['outcome'] == 'unknown':
        raise CheckError('dependency.condition-unknown', 'named condition needs a real decision', refs=[location])
    return when['outcome'] == 'true'


def check_relations(index):
    dependencies = {}
    symmetric = set()
    for uid, info in index.records.items():
        value = info['value']
        unique(value['constraints'], 'id', location=uid + '.constraints')
        unique(value['relationships'], 'id', location=uid + '.relationships')
        for entry in value['constraints'] + value['relationships']:
            location = uid + '/' + entry['id']
            ref = entry.get('target', entry.get('requirement'))
            if ref == uid:
                raise CheckError('relationship.self-reference', 'Requirement relation cannot target itself', refs=[location])
            target = index.target(ref)
            kind = entry.get('type', 'constraint')
            if kind in ('related-to', 'conflicts-with'):
                if isinstance(ref, str) and uid >= ref:
                    raise CheckError('relationship.storage-direction', 'same-scope symmetric relation is stored once at the smaller R ID', refs=[location])
                key = canonical_bytes([uid, ref, kind])
                if key in symmetric:
                    raise CheckError('relationship.duplicate', 'duplicate informational relationship', refs=[location])
                symmetric.add(key)
                if kind == 'conflicts-with':
                    if 'question_ref' not in entry:
                        raise CheckError('relationship.conflict-question', 'conflict needs one shared resolved Q', refs=[location])
                    q = index.questions.require_resolved(entry['question_ref'])
                    if not {uid, target['uid']} <= index.questions.impact(q['id'])['affected_requirements']:
                        raise CheckError('relationship.conflict-question', 'conflict Q does not cover both endpoints', refs=[location])
                continue
            # Background parents/related items do not silently become providers.
            if isinstance(ref, str) and ref not in index.records:
                raise CheckError('dependency.out-of-scope', 'current obligation provider must be in scope or explicitly external', refs=[location])
            target_acs = ac_subset(entry.get('target_acceptance', entry.get('acceptance')), target['acs'], location)
            applies = ac_subset(entry.get('applies_to', list(info['acs'])), info['acs'], location)
            for source in entry.get('source_refs', []):
                index.source_unit(source, info)
            active = condition(index.store, entry, location=location)
            if entry['strength'] == 'soft':
                if not entry.get('alternative') or not entry.get('review_ref'):
                    raise CheckError('dependency.soft-disposition', 'soft preference requires a reviewed fallback', refs=[location])
                evidence(index.store, entry['review_ref'])
            dependencies[location] = {'consumer': uid, 'applies_to': applies, 'target': target,
                                      'target_acceptance': target_acs, 'kind': kind, 'active': active,
                                      'strength': entry['strength'], 'entry': entry}
    # A cycle here is not automatically an execution deadlock: one candidate may
    # deliver mutually related requirements. S3 must check the mapped stage graph.
    return dependencies
