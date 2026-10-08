"""One target rule set; verify installed code/schema and exact dependency versions."""
from hashlib import sha256
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import platform
import sys

from .errors import CheckError, require
from .models import TOOL

CAPABILITIES = ("fixed-objects", "strict-models", "historical-decisions", "current-observation", "no-requirements-context")
CORE_CAPABILITIES = {"fixed-objects", "strict-models", "historical-decisions"}


def policy_capabilities(policy):
    required = set(policy["required_capabilities"])
    minimum = CORE_CAPABILITIES | ({"current-observation"} if policy["adoption"]["ui"] == "enabled" else set())
    require(minimum <= required <= set(CAPABILITIES), "rules.capability",
            "policy must require the applicable UI checks; unsupported capability cannot be ignored", "policy/required_capabilities")


def identity():
    path = TOOL / "config/rules.lock.json"
    try:
        raw = path.read_bytes(); lock = json.loads(raw)
    except (OSError, ValueError) as error:
        raise CheckError("rules.unreadable", str(error), path) from error
    require(lock.get("version") == "ui-check/1", "rules.version", "unsupported rule version", path)
    require(lock.get("capabilities") == list(CAPABILITIES), "rules.capability", "capability inventory differs from implementation", path)
    require(f"{sys.version_info.major}.{sys.version_info.minor}" == lock["python_minor"],
            "runtime.python", "use the declared isolated Python minor version", path)
    require(platform.system() == lock["platform"]["system"] and platform.machine() == lock["platform"]["machine"],
            "runtime.platform", "this distribution is verified only for the locked platform", path)
    actual = {str(p.relative_to(TOOL)) for folder in ["lib", "schemas"]
              for p in (TOOL / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    actual.update(["check.py", "ui-design-check", "config/requirements.lock"])
    require(actual == set(lock["files"]), "rules.inventory", "installed implementation file set differs from lock", path)
    for name, digest in lock["files"].items():
        target = TOOL / name
        require(not target.is_symlink() and sha256(target.read_bytes()).hexdigest() == digest,
                "rules.digest", "installed rule/schema/entry bytes differ from lock", name)
    for name, required in lock["dependencies"].items():
        try: installed = version(name)
        except PackageNotFoundError as error:
            raise CheckError("runtime.dependency", "missing " + name, path) from error
        require(installed == required, "runtime.dependency", f"{name} must be {required}, got {installed}", path)
    entry = os.environ.get("UI_DESIGN_ENTRY_PATH")
    if entry:
        actual_entry = Path(entry)
        require(actual_entry.is_file() and not actual_entry.is_symlink() and
                sha256(actual_entry.read_bytes()).hexdigest() == lock["files"]["ui-design-check"],
                "rules.entry", "invoked installed entry differs from the reviewed entry", actual_entry)
    return {"version": lock["version"], "sha256": sha256(raw).hexdigest()}


def implementation():
    """Return the complete verified inventory, rather than a library-only version."""
    rules = identity()
    lock = json.loads((TOOL / "config/rules.lock.json").read_text())
    return dict(rules=rules, files=lock["files"], dependencies=lock["dependencies"],
                python_minor=lock["python_minor"], platform=lock["platform"], capabilities=list(CAPABILITIES),
                invoked_entry=os.environ.get("UI_DESIGN_ENTRY_PATH", str(TOOL / "check.py")))
