"""共享 Q 的固定记录、决定与落实状态；不替责任人回答问题。"""
import re

from .core import digest
from .errors import CheckError
from .models import validate
from .reviews import decision, evidence


class QuestionIndex:
    def __init__(self, context, *, baseline_questions=None):
        self.context, self.store = context, context.store
        self.values, self.paths = {}, {}
        self.application_commits = {}
        if baseline_questions is not None and (baseline_questions.store is not self.store or
                baseline_questions.context.version != context.version):
            raise CheckError('question.owner-context', 'current questions must retain the selected baseline owner and delivery line')
        prefix = context.vr + '/questions/'
        for path in sorted(self.store.tree(context.content_commit)):
            if not path.startswith(prefix):
                continue
            name = path[len(prefix):]
            if not path.endswith('.yaml') and not name.startswith('Q-'):
                continue
            if not re.fullmatch(r'Q-[0-9]{3,}\.yaml', name):
                raise CheckError('question.path', 'one canonical questions/Q-NNN.yaml record per question', refs=[path])
            value = validate('question', self.store.yaml(context.content_commit, path), location=path)
            identity = context.version['version'] + '/' + name[:-5]
            if value['id'] != identity:
                raise CheckError('question.identity', 'question ID and owning file disagree', refs=[path])
            self.values[identity], self.paths[identity] = value, path
            application_commit = context.content_commit
            if baseline_questions is not None:
                old_path = baseline_questions.paths.get(identity)
                same = old_path == path and digest(self.store.read(context.content_commit, path)) == digest(
                    self.store.read(baseline_questions.context.content_commit, path))
                if same:
                    application_commit = baseline_questions.application_commits[identity]
                elif any('commit' not in ref for ref in value['applied_to']):
                    raise CheckError('question.fixed-application', 'new or changed engineering-stage Q must retain exact application commits', refs=[identity])
            self.application_commits[identity] = application_commit
        if baseline_questions is not None and not baseline_questions.values.keys() <= self.values.keys():
            raise CheckError('question.history-removed', 'current engineering Q cannot delete a baseline question; preserve its identity and history')
        for value in self.values.values():
            self._state(value)
        self.impacts = {}
        for identity, value in self.values.items():
            primary = self.resolve(identity)['id']
            impact = self.impacts.setdefault(primary, {key: set() for key in ('source_refs', 'affected_requirements', 'blocking_for')})
            for key in impact:
                impact[key].update(value[key])

    def canonical(self, identity):
        return self.context.version['version'] + '/' + identity if re.fullmatch(r'Q-[0-9]{3,}', identity) else identity

    def resolve(self, identity):
        identity = self.canonical(identity)
        visited = set()
        while True:
            if identity in visited:
                raise CheckError('question.duplicate-cycle', 'duplicate_of must end at one primary Q', refs=sorted(visited))
            visited.add(identity)
            value = self.values.get(identity)
            if value is None:
                raise CheckError('question.missing', 'question identity is absent from its fixed owner', refs=[identity])
            if value['status'] != 'duplicate':
                return value
            identity = self.canonical(value['duplicate_of'])

    def _state(self, value):
        identity, status = value['id'], value['status']
        if value['owner'] not in self.context.version['owners']:
            raise CheckError('question.owner', 'question owner must be a declared responsibility', refs=[identity])
        if any(name not in ('baseline', 'completion', 'release') and not re.fullmatch(r'C-[0-9]{3,}', name) for name in value['blocking_for']):
            raise CheckError('question.blocking-target', 'question blockers are baseline/completion/release or an explicit candidate ID', refs=[identity])
        response, verification = value['response'], value['verified_by']
        if response is not None:
            decision(self.context, response, roles={value['owner']})
        if verification is not None:
            decision(self.context, verification)
        applied = set()
        for ref in value['applied_to']:
            commit = ref.get('commit', self.application_commits[identity])
            key = (commit, ref['path'])
            if key in applied or ref['path'] == self.paths[identity]:
                raise CheckError('question.application', 'application evidence is duplicated or points to Q itself', refs=[identity])
            applied.add(key)
            self.store.ref(ref, default_commit=self.application_commits[identity])
        if status in ('open', 'duplicate') and (response is not None or verification is not None or applied):
            raise CheckError('question.state', 'open/duplicate records cannot carry an active resolved answer', refs=[identity])
        if status == 'duplicate':
            if not value.get('duplicate_of'):
                raise CheckError('question.duplicate-target', 'duplicate Q requires its primary identity', refs=[identity])
        elif 'duplicate_of' in value:
            raise CheckError('question.state', 'only a duplicate record carries duplicate_of', refs=[identity])
        if status in ('answered', 'resolved') and response is None:
            raise CheckError('question.answer-required', 'a real response is required', refs=[identity])
        if status == 'answered' and verification is not None:
            raise CheckError('question.state', 'verified completion must be recorded as resolved', refs=[identity])
        if status == 'resolved' and (not applied or verification is None):
            raise CheckError('question.application-required', 'resolved requires actual application and verification', refs=[identity])
        if status == 'deferred':
            if not value.get('disposition_ref'):
                raise CheckError('question.disposition-required', 'deferral needs a retained scope decision', refs=[identity])
            evidence(self.store, value['disposition_ref'])
        if status == 'reopened':
            if not value.get('reopened_reason') or not value.get('reopened_ref'):
                raise CheckError('question.reopen-reason', 'reopening must preserve a reason and evidence', refs=[identity])
            evidence(self.store, value['reopened_ref'])

    def require_resolved(self, identity, *, scope_decision=False):
        value = self.resolve(identity)
        deferred = scope_decision and value['status'] == 'deferred'
        if value['status'] != 'resolved' and not deferred:
            raise CheckError('question.unresolved', 'a baseline obligation still depends on an unresolved Q', refs=[value['id']])
        if deferred and (not value['applied_to'] or value['verified_by'] is None):
            raise CheckError('question.application-required', 'deferred scope decision has not been applied and verified', refs=[value['id']])
        if scope_decision:
            if value['response'] is None:
                raise CheckError('question.answer-required', 'scope exclusion requires an actual product decision', refs=[value['id']])
            decision(self.context, value['response'], roles={'product-owner'})
        return value

    def impact(self, identity):
        return self.impacts[self.resolve(identity)['id']]

    def check_endpoints(self, units, requirements, *, candidates=None):
        for value in self.values.values():
            if not set(value['source_refs']) <= set(units):
                raise CheckError('question.source', 'Q references an unknown source unit', refs=[value['id']])
            if not set(value['affected_requirements']) <= set(requirements):
                raise CheckError('question.requirement', 'Q references an unknown Requirement', refs=[value['id']])
            if candidates is not None and not (set(value['blocking_for']) - {'baseline', 'completion', 'release'}) <= set(candidates):
                raise CheckError('question.candidate', 'Q references an unknown candidate', refs=[value['id']])

    def check_baseline(self, included):
        # Duplicating a question must never discard its original impact set.
        # Decisions belong to the primary Q; impact is the union of all aliases.
        for identity, group in self.impacts.items():
            if 'baseline' not in group['blocking_for']:
                continue
            resolved = self.values[identity]
            if resolved['status'] == 'deferred' and not group['affected_requirements'] & set(included):
                self.require_resolved(identity, scope_decision=True)
            else:
                self.require_resolved(identity)
