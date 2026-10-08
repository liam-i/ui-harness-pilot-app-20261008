"""依赖及固定官方源码预检；没有安装、副作用或来源回退。"""
from importlib import metadata, util
from pathlib import Path
import os
import re
import sys

from .core import digest, parse_json, local_file
from .errors import InputError

HOME = Path(__file__).resolve().parents[1]


PREFIX = "harness/version-requirements/"
UI_PREFIX = "harness/ui-design/"


def implementation_manifest(*, ui=False):
    """One installation identity, using canonical project paths.

    UI is an explicit adoption mode, not inferred from an optional sidecar.
    Policy is fixed data added by reviewed_implementation, not executable code.
    """
    files = [p for directory in ("lib", "schemas") for p in sorted((HOME / directory).rglob("*"))
             if p.is_file() and p.suffix in (".py", ".json")]
    files += [HOME / name for name in ("config/runtime.json", "config/requirements.lock",
                                       "review.py", "requirements-check")]
    result = {PREFIX + p.relative_to(HOME).as_posix(): digest(p.read_bytes()) for p in files}
    result["scripts/requirements-check"] = digest((HOME / "requirements-check").read_bytes())
    if ui:
        source = HOME.parent / "ui-design"
        try:
            lock = parse_json(local_file(source, "config/rules.lock.json").read_bytes())
            names = set(lock["files"]) | {"config/rules.lock.json"}
            # The common runtime verifies its own lock/dependencies. This full
            # inventory also rejects files absent from the declared lock.
            names.update(p.relative_to(source).as_posix()
                         for folder in ("lib", "schemas") for p in (source / folder).rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts)
            for name in sorted(names):
                result[UI_PREFIX + name] = digest(local_file(source, name).read_bytes())
            result["scripts/ui-design-check"] = digest(local_file(source, "ui-design-check").read_bytes())
        except (OSError, KeyError, TypeError) as error:
            raise InputError("rules.ui-missing", "enabled UI needs its complete separately installed shared tool") from error
    return result


def ui_runtime():
    """Load the explicitly installed common module; never a second validator."""
    from importlib import import_module
    source = HOME.parent / "ui-design"
    if not (source / "lib/ui_design/runtime.py").is_file():
        raise InputError("rules.ui-missing", "enabled UI needs the installed common library")
    sys.path.insert(0, str(source / "lib"))
    try:
        module = import_module("ui_design.runtime")
        if module.TOOL.resolve() != source.resolve():
            raise InputError("rules.ui-source", "a different UI library is already loaded")
        try:
            module.identity()
        except Exception as error:
            from ui_design.errors import CheckError
            if not isinstance(error, CheckError):
                raise
            raise InputError("rules.ui-identity", str(error), refs=[error.diagnostic]) from error
        return module
    finally:
        sys.path.pop(0)


def preflight(*, ui=False):
    contract = parse_json((HOME / "config/runtime.json").read_bytes())
    entry = os.environ.get('REQUIREMENTS_CHECK_ENTRY_PATH')
    if entry is not None and digest(Path(entry).read_bytes()) != digest((HOME / 'requirements-check').read_bytes()):
        raise InputError('runtime.entry', 'invoked requirements-check differs from the installed canonical entry')
    if sys.prefix == sys.base_prefix:
        raise InputError("runtime.venv", "run inside the explicitly installed isolated venv")
    if ".".join(map(str, sys.version_info[:2])) != contract["python_minor"]:
        raise InputError("runtime.python", "unsupported Python minor; qualification is required")
    packages = {}
    lock = (HOME / "config/requirements.lock").read_text()
    for name, version in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", lock, re.M):
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError as error:
            raise InputError("runtime.missing-package", "missing pinned package: " + name) from error
        if actual != version:
            raise InputError("runtime.package-version", f"{name}: expected {version}, got {actual}")
        packages[name] = actual
    if len(packages) != contract["package_count"]:
        raise InputError("runtime.lock", "lock package inventory mismatch")
    for module, files in contract["source_files"].items():
        spec = util.find_spec(module)
        if spec is None or spec.origin is None:
            raise InputError("runtime.source", "cannot locate package: " + module)
        root = Path(spec.origin).parent
        for path, expected in files.items():
            try:
                actual = digest((root / path).read_bytes())
            except OSError as error:
                raise InputError("runtime.source", str(error)) from error
            if actual != expected:
                raise InputError("runtime.source", "pinned source mismatch", refs=[module + "/" + path])
    return {"checker_version": "vr-check/2", "rule_version": "vr-rules/2", "python": sys.version,
            "implementation_files": implementation_manifest(ui=ui),
            "ui_implementation": ui_runtime().implementation() if ui else None,
            "packages": packages, "lock_sha256": digest(lock.encode()), "runtime_sha256": digest((HOME / "config/runtime.json").read_bytes()),
            "support": contract["support"]}


def reviewed_implementation(context):
    """Require the one target implementation in current and historical mode.

    Fixed historical bytes are never executed or admitted through a registry.
    A fixed policy remains data at its own business time, included in the same
    Review manifest, while executable bytes must match this installed release.
    """
    ui = context.configuration["ui_design"] == "enabled"
    current = implementation_manifest(ui=ui)
    tree = context.store.tree(context.content_commit)
    def governed(path):
        for prefix in (PREFIX, UI_PREFIX) if ui else (PREFIX,):
            if path.startswith(prefix):
                local = path[len(prefix):]
                return ((local.startswith(("lib/", "schemas/")) and
                         (prefix == UI_PREFIX or path.endswith((".py", ".json")))) or
                        local in ("config/runtime.json", "config/requirements.lock", "config/rules.lock.json",
                                  "review.py", "requirements-check", "check.py", "ui-design-check"))
        return path in ("scripts/requirements-check", "scripts/ui-design-check") if ui else path == "scripts/requirements-check"
    paths = {path for path in tree if governed(path)}
    if paths != set(current):
        raise InputError("rules.snapshot-mismatch", "fixed implementation inventory differs from the single installed target", refs=sorted(paths ^ set(current)))
    for path, expected in current.items():
        if digest(context.store.read(context.content_commit, path)) != expected:
            raise InputError("rules.snapshot-mismatch", "fixed rule/schema/entry differs from the installed target", refs=[path])
    if ui:
        path = UI_PREFIX + "config/project.yaml"
        current[path] = digest(context.store.read(context.content_commit, path))
    return current


def selected_runtime(context):
    """Attach the installed code and fixed policy identity to a Gate result."""
    result = preflight(ui=context.configuration['ui_design'] == 'enabled')
    result['implementation_files'] = reviewed_implementation(context)
    if context.configuration['ui_design'] == 'enabled':
        from ui_design.models import parse, validate
        from ui_design.errors import CheckError
        path = UI_PREFIX + 'config/project.yaml'
        try:
            policy = validate('policy', parse(context.store.read(context.content_commit, path), path), path)
            ui_runtime().policy_capabilities(policy)
        except CheckError as error:
            raise InputError('ui.policy', str(error), refs=[error.diagnostic]) from error
        if policy['adoption'] != {'ui': 'enabled', 'requirements': 'adopted'}:
            raise InputError('ui.policy-adoption', 'UI policy must explicitly adopt this requirements layer')
        result['capabilities'] = ['requirements-gates', 'ui-fixed-inputs', 'ui-current-observation']
    else:
        result['capabilities'] = ['requirements-gates']
    return result
