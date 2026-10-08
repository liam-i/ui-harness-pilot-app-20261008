"""官方 Doorstop 的受保护只读验证；写操作仍由授权阶段显式调用。"""
from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .core import digest, parse_yaml, snapshot
from .errors import CheckError, InputError
from .models import check_requirement_ids

STRICT = ["--no-reformat", "--no-level-check", "--warn-all", "--error-all"]


def valid_stamp(stamp):
    try:
        return (isinstance(stamp, str) and len(stamp) == 44
                and len(base64.b64decode(stamp, altchars=b"-_", validate=True)) == 32)
    except ValueError:
        return False


def projection_precheck(root):
    root = Path(root)
    before = snapshot(root, times=True)
    paths = sorted((root / "requirements/items").rglob("R-*.yml"))
    if not paths:
        raise CheckError("doorstop.empty", "no selected records")
    if len({p.stem for p in paths}) != len(paths):
        raise CheckError("doorstop.duplicate", "duplicate UID in projection")
    check_requirement_ids(p.stem for p in paths)
    for path in paths:
        record = parse_yaml(path.read_bytes())
        if not isinstance(record, dict) or not valid_stamp(record.get("reviewed")):
            raise CheckError("doorstop.review-required", "explicit native review required before strict validation", refs=[path.stem])
    return before


def verify_records(records):
    """records: UID -> {bytes, configuration, record_ref, configuration_ref}.

    每组保持原配置字节；函数只写自己的临时投影。返回实际调用及输入身份，
    不返回产品批准，也不把其他草稿加入所选 scope。
    """
    if not records:
        raise CheckError("doorstop.empty", "no selected records")
    check_requirement_ids(records)
    groups = {}
    for uid, info in records.items():
        groups.setdefault(digest(info["configuration"]), []).append((uid, info))
    results = []
    for config_digest, group in sorted(groups.items()):
        with tempfile.TemporaryDirectory(prefix="vr-doorstop-") as temporary:
            root = Path(temporary)
            items = root / "requirements/items"
            items.mkdir(parents=True)
            (items / ".doorstop.yml").write_bytes(group[0][1]["configuration"])
            for uid, info in group:
                (items / (uid + ".yml")).write_bytes(info["bytes"])
            before = projection_precheck(root)
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k not in ("PYTHONPATH", "PYTHONHOME")}
            env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0",
                       GIT_TERMINAL_PROMPT="0", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
            argv = [sys.executable, "-I", "-B", str(Path(sys.executable).parent / "doorstop"),
                    "--project", str(root), *STRICT]
            try:
                result = subprocess.run(argv, cwd=root, env=env, capture_output=True, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise InputError("doorstop.tool", str(error)) from error
            if snapshot(root, times=True) != before:
                raise InputError("doorstop.unexpected-write", "native validation changed its projection; result invalid",
                                 refs=[uid for uid, _ in group])
            details = {"configuration_sha256": config_digest, "records": [uid for uid, _ in group],
                       "exit_code": result.returncode, "stdout": result.stdout.decode(errors="replace"),
                       "stderr": result.stderr.decode(errors="replace")}
            if result.returncode:
                raise CheckError("doorstop.strict", str(details), refs=[uid for uid, _ in group])
            results.append(details)
    return results
