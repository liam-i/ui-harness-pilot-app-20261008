"""人工审阅记录的身份与完整输入绑定；机器不替代业务判断。"""
from .core import canonical_bytes, digest
from .errors import CheckError
from .models import unique, validate


def evidence(store, reference):
    data = store.ref(reference)
    if not data.strip():
        raise CheckError("evidence.empty", "empty evidence is not a review/decision", refs=[reference])
    return data


def decision(context, value, *, roles=None):
    validate("decision", value)
    role = value["role"]
    if (roles and role not in roles) or context.version["owners"].get(role) != value["actor"]:
        raise CheckError("review.actor", "decision actor/role does not match version responsibility", refs=[role])
    evidence(context.store, value["evidence_ref"])


def review_input_digest(inputs, context_refs=()):
    """共同绑定业务与工程语境；空语境保持已有接收记录的摘要表示。"""
    ordered = sorted(inputs, key=canonical_bytes)
    value = {'reviewed_inputs': ordered, 'context_refs': sorted(context_refs, key=canonical_bytes)} if context_refs else ordered
    return digest(canonical_bytes(value))


def check_review(context, relative, phase, required_paths, *, source_units=None, required_checks=(), roles=None,
                 required_refs=(), required_context_refs=()):
    review = context.read(relative, "review")
    if review["phase"] != phase or review["outcome"] != "passed":
        raise CheckError("review.incomplete", "required review has not passed for this phase", refs=[relative])
    if (phase != 'batch' and 'reviewed_requirements' in review) or (
            phase != 'engineering' and any(field in review for field in ('engineering', 'dependency_dispositions'))):
        raise CheckError('review.phase-fields', 'phase-specific Review fields are in the wrong record', refs=[relative])
    role = review["role"]
    if (roles and role not in roles) or context.version["owners"].get(role) != review["actor"]:
        raise CheckError("review.actor", "reviewer does not match the declared responsibility", refs=[relative])
    evidence(context.store, review["evidence_ref"])
    def bind(items):
        result = {}
        for item in items:
            revision = item.get('commit', context.content_commit)
            key = (revision, item['path'])
            if key in result:
                raise CheckError('review.duplicate-input', 'duplicate review input/context', refs=[item])
            if key == (context.content_commit, context.vr + '/' + relative):
                raise CheckError('review.self-reference', 'Review cannot contain its own current hash', refs=[relative])
            context.store.ref(item, default_commit=context.content_commit)
            result[key] = item['sha256']
        return result
    bound = bind(review['reviewed_inputs'])
    for path in sorted(required_paths):
        expected = digest(context.store.read(context.content_commit, path))
        if bound.get((context.content_commit, path)) != expected:
            raise CheckError("review.binding", "review does not bind the complete current input", refs=[path])
    contextual = bind(review['context_refs'])
    for required, actual in ((required_refs, bound), (required_context_refs, contextual)):
        for ref in required:
            context.store.ref(ref, default_commit=context.content_commit)
            key = (ref.get('commit', context.content_commit), ref['path'])
            if actual.get(key) != ref['sha256']:
                raise CheckError('review.binding', 'review does not bind the exact required input/context', refs=[ref])
    checks = unique(review["checks"], "check_id", location=relative)
    expected_digest = review_input_digest(review['reviewed_inputs'], review['context_refs'])
    for item in checks.values():
        if item["input_digest"] != expected_digest:
            raise CheckError("review.check-binding", "check does not bind the reviewed input set", refs=[item["check_id"]])
        evidence(context.store, item["evidence_ref"])
        if not set(item["source_units"]) <= set(review["processed_units"]):
            raise CheckError("review.check-coverage", "check claims unprocessed source units", refs=[item["check_id"]])
    for name in required_checks:
        if name not in checks or checks[name]["outcome"] != "passed":
            raise CheckError("review.required-check", "required human check is absent or not passed", refs=[name])
    if any(item["outcome"] in ("failed", "unreadable") for item in review["checks"]):
        raise CheckError("review.failed-check", "a recorded review check is unresolved", refs=[relative])
    if source_units is not None:
        if not set(source_units) <= set(review["processed_units"]) or set(source_units) & set(review["pending_units"]):
            raise CheckError("review.source-coverage", "selected source units have not all been reviewed", refs=[relative])
        checked_units = {unit for check in checks.values() if check['check_id'] in required_checks for unit in check['source_units']}
        if required_checks and not set(source_units) <= checked_units:
            raise CheckError('review.check-coverage', 'required checks do not cover the declared processed source units', refs=[relative])
    if set(review['processed_units']) & set(review['pending_units']):
        raise CheckError('review.source-coverage', 'a source unit cannot be both processed and pending', refs=[relative])
    return review
