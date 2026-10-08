#!/usr/bin/env python3
"""Bind a reviewed UI CI selection to the actual checked SHA and shared checker."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ui-repository", type=Path, required=True)
    parser.add_argument("--config", required=True, help="reviewed configuration path inside the checked Git commit")
    parser.add_argument("--head", required=True, help="independent host PR head, not a branch name")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from ui_design.models import parse
    from ui_design.objects import Repository
    from ui_design.api import check
    result = {"result": "FAIL", "engineering_authorized": False, "current_permission": False}
    try:
        root = args.root.resolve(strict=True)
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.head):
            raise ValueError("host must supply a full checked SHA")
        repo = Repository(root)
        if repo.git("rev-parse", "HEAD").decode().strip() != args.head:
            raise ValueError("host SHA differs from checkout")
        if repo.git("status", "--porcelain=v1").strip():
            raise ValueError("checked checkout must be clean")
        config = parse(repo.read(args.head, args.config), args.config)
        if set(config) != {"business_repository", "ui_repository", "policy_path", "bindings_path", "snapshot"}:
            raise ValueError("unexpected CI configuration fields")
        snapshot = config["snapshot"]
        if snapshot.get("mode") != "current" or snapshot.get("action") != "pre-merge":
            raise ValueError("CI selection must explicitly require current pre-merge UI checking")
        if any(k in snapshot for k in ("repositories", "policy_ref", "bindings_ref")) or "head" in snapshot["subject"]:
            raise ValueError("physical mappings and actual host SHA are supplied only by this adapter")
        business, ui = config["business_repository"], config["ui_repository"]
        if not business or not ui or business == ui:
            raise ValueError("business and UI repository identities must be distinct")
        snapshot["repositories"] = {business: str(root), ui: str(args.ui_repository.resolve(strict=True))}
        snapshot["subject"]["head"] = {"repository": business, "commit": args.head}
        for name in ("policy", "bindings"):
            path = config[name + "_path"]
            raw = repo.read(args.head, path)
            snapshot[name + "_ref"] = {"repository": business, "commit": args.head, "path": path,
                                       "sha256": sha256(raw).hexdigest()}
        checked = check(snapshot, root)
        result.update(result=checked["result"], head=args.head, snapshot=snapshot, check=checked,
                      adapter_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
        # A fixed-time success or a non-UI bypass cannot satisfy this UI Job.
        if checked["result"] == "PASS" and not (checked.get("current_checked") and checked.get("ui_required")):
            raise ValueError("this UI CI Job requires a real current authority observation and selected UI package")
    except Exception as error:
        result.update(result="FAIL", diagnostic=getattr(error, "diagnostic", {"code": "ci.inputs", "message": str(error)}))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"result": result["result"], "head": result.get("head"), "output": str(args.output)}))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
