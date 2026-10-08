"""Public fixed-input API; failures remain data, never permissions."""
from .errors import CheckError, require
from .models import validate
from .objects import Store, key
from .runtime import identity, implementation
from .validation import Validator


def _fixed(snapshot, root):
    result = {"schema_version": "ui-result/1", "result": "FAIL", "mode": snapshot.get("mode") if isinstance(snapshot, dict) else None,
              "engineering_authorized": False, "current_permission": False, "rules": None, "inputs": [], "packages": [],
              "diagnostics": [], "proof_scope": "fixed-time bytes, declared identities and decision history; no remote observation or human impersonation"}
    store = None
    try:
        rules = identity(); result["rules"] = rules; result["implementation"] = implementation()
        validate("snapshot", snapshot, "snapshot")
        require(snapshot["rules"] == rules, "rules.identity", "snapshot rules differ from installed fixed implementation", "snapshot/rules")
        store = Store(snapshot["repositories"], root)
        validator = Validator(store, snapshot, root)
        validator.consume()
        result.update(result="PASS", authorities=validator.history.audit, consumers=validator.consumers, ui_required=validator.requires_ui,
                      external_objects=validator.external_objects,
                      packages=[{"package_ref": p["ref"], "unit": p["document"]["unit"], "release": p["document"]["release"],
                                 "files": p["files"], "external_inputs": p["external_inputs"], "dependencies": p["document"]["dependencies"]}
                                for _, p in sorted(validator.packages.items())])
    except CheckError as error:
        result["diagnostics"].append(error.diagnostic)
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        result["diagnostics"].append(dict(code="input.unreadable", message=str(error), source="fixed input", location=""))
    if store:
        result["inputs"] = [v for _, v in sorted(store.inputs.items())]
    return result


def check(snapshot, root):
    """Shared fixed validator, with an explicit live observer only for current."""
    fixed = _fixed(snapshot, root)
    if isinstance(snapshot, dict) and snapshot.get("mode") == "current":
        from .observation import current
        return current(snapshot, root, fixed)
    return fixed
