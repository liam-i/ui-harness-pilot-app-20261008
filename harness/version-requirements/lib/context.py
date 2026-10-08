"""阶段快照、版本身份与当前/历史查询的共同约束。"""
from dataclasses import dataclass, replace
import re

from .core import digest, parse_yaml
from .errors import CheckError, InputError
from .models import validate

PHASES = {("G0", "intake"): "intake:", ("G1", "content"): "version:",
          ("G1", "record"): "baseline:", ("G1", "effective"): "baseline:",
          ("G2", "dispatch"): "candidate:", ("G2", "planning"): "candidate:",
          ("G2", "apply"): "candidate:", ("G3", "pre-archive"): "change:",
          ("G3", "pre-merge"): "change:", ("G3", "integrated"): "change:",
          ("G4", "completion"): "release-candidate:", ("G4", "release"): "release-candidate:"}


@dataclass
class Context:
    store: object
    snapshot: dict
    version: dict
    configuration: dict
    baseline: dict | None
    vr: str
    content_commit: str

    def read(self, relative, kind):
        path = self.vr + "/" + relative
        return validate(kind, self.store.yaml(self.content_commit, path), location=path)

    def at(self, commit, version):
        """历史内容的所有者语境；只解析身份，不宣称该历史 BL 已生效。"""
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
            raise InputError("context.owner", "canonical owner Version required")
        vr = "requirements/versions/" + version
        data = validate("version", self.store.yaml(commit, vr + "/version.yaml"))
        if data["version"] != version:
            raise CheckError("context.owner", "fixed owner Version and path disagree")
        return replace(self, content_commit=commit, version=data, vr=vr, baseline=None)


def phase_identity(snapshot):
    validate("snapshot", snapshot, location="context")
    prefix = PHASES.get((snapshot["gate"], snapshot["phase"]))
    if prefix is None:
        raise InputError("gate.unsupported", "this release does not implement the requested gate/phase")
    qualification = snapshot['gate'] == 'G4'
    if qualification:
        forbidden = ('dispatch_ref', 'trace_ref', 'apply_request_ref', 'apply_origin_ref', 'planning_inputs_ref',
                     'pre_archive_context_ref', 'final_checks_ref', 'merge_request_ref', 'integration_checks_ref',
                     'slot_release_ref', 'tiny_ref', 'integration_observation_ref')
        if any(key in snapshot for key in forbidden):
            raise InputError('snapshot.qualification', 'Version qualification consumes retained delivery receipts, not a new Change admission')
    elif any(key in snapshot for key in ('release_candidate_ref', 'release_decision_ref', 'release_observation_ref')):
        raise InputError('snapshot.qualification', 'release candidate/decision/observation belong only to G4')
    if 'release_observation_ref' in snapshot and snapshot['phase'] != 'release':
        raise InputError('snapshot.release-observation', 'actual release confirmation belongs only to the release phase')
    tiny = (snapshot['gate'] == 'G3' and snapshot['phase'] in ('pre-merge', 'integrated') and
            snapshot['subject'].startswith(('task:', 'pr:')))
    if tiny:
        validate('tiny_subject', snapshot['subject'])
        prefix = snapshot['subject'].split(':', 1)[0] + ':'
        forbidden = ('dispatch_ref', 'trace_ref', 'apply_request_ref', 'apply_origin_ref',
                     'planning_inputs_ref', 'pre_archive_context_ref', 'slot_release_ref')
        if any(key in snapshot for key in forbidden):
            raise InputError('snapshot.tiny-delivery', 'Tiny uses its actual task/PR, not Change, Apply, Archive or reservation inputs')
    if 'tiny_ref' in snapshot and not tiny:
        raise InputError('snapshot.tiny-delivery', 'task/PR association belongs only to Tiny delivery')
    if 'integration_observation_ref' in snapshot and not (tiny and snapshot['phase'] == 'integrated'):
        raise InputError('snapshot.tiny-integration', 'a direct integration observation belongs only to integrated Tiny delivery')
    if (snapshot['gate'], snapshot['phase']) == ('G3', 'integrated') and snapshot['subject'].startswith('scope:'):
        prefix = 'scope:'
        forbidden = ('dispatch_ref', 'trace_ref', 'apply_request_ref', 'apply_origin_ref',
                     'planning_inputs_ref', 'pre_archive_context_ref', 'final_checks_ref',
                     'merge_request_ref', 'integration_checks_ref', 'slot_release_ref')
        if any(key in snapshot for key in forbidden):
            raise InputError('snapshot.scope-delivery', 'scope delivery has no Change, Apply, Archive, merge or capacity event')
    delivery_phase = snapshot['gate'] == 'G3' and snapshot['phase'] in ('pre-archive', 'pre-merge', 'integrated')
    pre_merge = (snapshot['gate'], snapshot['phase']) == ('G3', 'pre-merge')
    integrated = (snapshot['gate'], snapshot['phase']) == ('G3', 'integrated')
    if (('engineering_inputs' in snapshot and not (integrated or tiny or qualification)) or
            (any(key in snapshot for key in ('integration_checks_ref', 'slot_release_ref')) and not integrated)):
        raise InputError('snapshot.engineering-inputs', 'current engineering inputs require integrated or Tiny pre-merge; integration-only inputs require integrated')
    if any(key in snapshot for key in ('pre_archive_context_ref', 'final_checks_ref', 'merge_request_ref')) and not pre_merge:
        raise InputError('snapshot.pre-merge-inputs', 'final delivery inputs belong only to pre-merge')
    publication = snapshot.get('publication_revision')
    observation = snapshot.get('publication_evidence_ref')
    if bool(publication) != bool(observation) or ((publication or observation) and prefix not in ('baseline:', 'candidate:', 'change:', 'scope:', 'task:', 'pr:', 'release-candidate:')):
        raise InputError('snapshot.publication', 'paired original BL publication context belongs to baseline or implemented downstream phases')
    if snapshot.get('dispatch_ref') is not None and prefix not in ('candidate:', 'change:'):
        raise InputError('snapshot.dispatch', 'dispatch event reference belongs only to an implemented candidate or delivery phase')
    if snapshot.get('trace_ref') is not None and (snapshot['gate'], snapshot['phase']) not in (('G2', 'planning'), ('G2', 'apply')) and not delivery_phase:
        raise InputError('snapshot.trace', 'Trace reference belongs only to implemented planning, Apply or delivery phases')
    if snapshot.get('apply_request_ref') is not None and (snapshot['gate'], snapshot['phase']) != ('G2', 'apply') and not delivery_phase:
        raise InputError('snapshot.apply-request', 'implementation request belongs only to Apply admission or delivery verification')
    if snapshot.get('apply_origin_ref') is not None and (snapshot['gate'], snapshot['phase']) not in (('G2', 'apply'), ('G2', 'planning')) and not delivery_phase:
        raise InputError('snapshot.apply-origin', 'original implementation admission belongs only to Apply, its planning revision or delivery verification')
    if snapshot.get('planning_inputs_ref') is not None and (
            (snapshot['gate'], snapshot['phase']) != ('G2', 'planning') or snapshot.get('apply_origin_ref') is None):
        raise InputError('snapshot.planning-inputs', 'reviewed execution inputs belong only to post-Apply planning with its original admission')
    if 'verification_inputs' in snapshot and not (delivery_phase or qualification):
        raise InputError('snapshot.verification-inputs', 'delivery execution expectations belong only to an implemented delivery phase')
    if not snapshot["subject"].startswith(prefix):
        raise InputError("snapshot.subject", "typed subject does not match phase")
    identity = snapshot["subject"][len(prefix):]
    version = snapshot["version"]
    if prefix == "version:" and identity != version:
        raise InputError("snapshot.subject", "version subject disagrees with snapshot version")
    if prefix == "intake:" and (not identity.startswith(version + "/intake-") or
                               not identity.removeprefix(version + "/intake-").isdigit()):
        raise InputError("snapshot.subject", "intake must belong to the selected Version")
    if prefix == "baseline:" and not identity.startswith("BL-" + version + "-"):
        raise InputError("snapshot.subject", "baseline must belong to the selected Version")
    if prefix == 'candidate:' and not re.fullmatch(re.escape(version) + r'/C-[0-9]{3,}', identity):
        raise InputError('snapshot.subject', 'candidate must belong to the selected Version')
    if prefix == 'change:' and not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', identity):
        raise InputError('snapshot.subject', 'Change subject requires its logical kebab-case name, not an archive path')
    if prefix == 'scope:' and not re.fullmatch(re.escape(version) + r'(?:/R-[0-9]{3,}(?:/AC-[0-9]{2,})?)?', identity):
        raise InputError('snapshot.subject', 'scope must select this Version, an included R, or one of its ACs')
    if prefix == 'release-candidate:' and not re.fullmatch(re.escape(version) + r'/candidate-[0-9]{3,}', identity):
        raise InputError('snapshot.subject', 'release candidate must belong to the selected Version')
    if prefix not in ('baseline:', 'candidate:', 'change:', 'scope:', 'task:', 'pr:', 'release-candidate:') and snapshot["baseline_ref"] is not None:
        raise InputError("snapshot.future-baseline", "G0/intake and G1/content do not use a baseline descriptor")
    if prefix in ('baseline:', 'candidate:', 'change:', 'scope:', 'task:', 'pr:', 'release-candidate:') and snapshot["baseline_ref"] is None:
        raise CheckError("snapshot.baseline-required", "this phase requires an existing fixed baseline descriptor")
    return identity


def resolve(store, snapshot):
    identity = phase_identity(snapshot)
    for key in ("metadata_revision", "head_revision", "target_revision"):
        store.commit(snapshot[key])
    if snapshot["control_revision"]:
        store.commit(snapshot["control_revision"])
    vr = "requirements/versions/" + snapshot["version"]
    content = snapshot["head_revision"]
    baseline = None
    if snapshot["baseline_ref"]:
        reference = snapshot["baseline_ref"]
        downstream = snapshot['gate'] in ('G2', 'G3', 'G4')
        if downstream:
            data = store.ref(reference)
            baseline = validate("baseline", parse_yaml(data), location=reference['path'])
            identity = baseline['id']
            content = baseline['content_commit']
        expected_path = vr + "/baselines/" + identity + ".yaml"
        if reference["path"] != expected_path:
            raise InputError("snapshot.baseline-path", "baseline ID and fixed record path disagree")
        if not downstream:
            data = store.ref(reference)
            baseline = validate("baseline", parse_yaml(data), location=expected_path)
        if baseline["id"] != identity or baseline["version"] != snapshot["version"] or baseline["content_commit"] != content:
            raise InputError("snapshot.baseline-content", "mixed baseline/content/version snapshot")
        # Later evidence metadata may follow B, but cannot carry a different descriptor.
        store.read(snapshot["metadata_revision"], expected_path, digest(data))
    version_path = vr + "/version.yaml"
    version = validate("version", store.yaml(content, version_path), location=version_path)
    if (version["version"], version["delivery_line"]) != (snapshot["version"], snapshot["delivery_line"]):
        raise InputError("snapshot.version-line", "version/line differs from fixed version.yaml")
    store.commit(version["starting_commit"])
    config_path = "harness/version-requirements/config/project.yaml"
    configuration = validate("project_config", store.yaml(content, config_path), location=config_path)
    from .ui_integration import require_entry
    require_entry(configuration, snapshot)
    store.ref(configuration["protection_evidence_ref"])
    if snapshot["evaluation_mode"] == "current":
        names = [version["integration_ref"]]
        if snapshot["control_revision"]:
            names.append(configuration["control_ref"])
        actual = store.remote_refs(configuration["authority_remote"], names)
        if actual.get(version["integration_ref"]) != snapshot["target_revision"]:
            raise CheckError("snapshot.stale-target", "snapshot target does not match the current authority remote")
        if snapshot["control_revision"] and actual.get(configuration["control_ref"]) != snapshot["control_revision"]:
            raise CheckError("snapshot.stale-control", "snapshot control does not match the current authority remote")
    return Context(store, snapshot, version, configuration, baseline, vr, content)
