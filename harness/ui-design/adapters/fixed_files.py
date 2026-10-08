#!/usr/bin/env python3
"""Export checked Git-native design files; never approve or start engineering."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import sys

sys.dont_write_bytecode = True
TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "lib"))


def relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p in ("", ".", "..") for p in path.parts) or "\\" in value:
        raise ValueError("unsafe export path: " + value)
    return path


def export(snapshot, root, destination):
    from ui_design.api import check
    from ui_design.objects import Store

    checked = check(snapshot, root)
    result = {"result": "FAIL", "check": checked, "engineering_authorized": False,
              "current_permission": False, "diagnostics": []}
    if checked["result"] != "PASS":
        return result
    try:
        if not checked["packages"]:
            raise ValueError("no approved design package selected for export")
        if checked.get("external_objects"):
            raise ValueError("this adapter requires Git-native files; use the declared external media delivery path")
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise ValueError("output already exists; choose a new directory")
        destination = destination.resolve()
        if not destination.parent.is_dir():
            raise ValueError("output parent must already exist")
        store = Store(snapshot["repositories"], root)
        for mapping in snapshot["repositories"].values():
            source = Path(mapping)
            source = (source if source.is_absolute() else Path(root) / source).resolve()
            if destination.is_relative_to(source):
                raise ValueError("output must be outside every input repository")

        files = {}
        origins = {}
        for package in checked["packages"]:
            base = PurePosixPath("packages") / relative(package["unit"]) / relative(package["release"])
            manifest = package["package_ref"]
            directory = PurePosixPath(manifest["path"]).parent
            for ref in [manifest, *package["files"]]:
                target = str(base / relative(str(PurePosixPath(ref["path"]).relative_to(directory))))
                if target in files:
                    raise ValueError("duplicate export destination: " + target)
                files[target] = store.read(ref)
                origins[target] = ref

        # Validation and all source reads finish before creating any output.
        # mkdir is exclusive; a failed partial export is never silently reused.
        destination.mkdir()
        inventory = {}
        for name, data in sorted(files.items()):
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            inventory[name] = {"ref": origins[name], "sha256": sha256(data).hexdigest(), "bytes": len(data)}
        receipt = {"adapter": "fixed-git-files/1", "adapter_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                   "recorded_at": datetime.now(timezone.utc).isoformat(), "check": checked, "files": inventory,
                   "scope": "Disposable byte-preserving export; not Git history backup, design approval or engineering permission."}
        with (destination / "receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        result.update(result="PASS", output=str(destination), file_count=len(files),
                      receipt_sha256=sha256((destination / "receipt.json").read_bytes()).hexdigest())
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["diagnostics"].append({"code": "export.failed", "message": str(error)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        from ui_design.models import parse
        context = Path(args.context)
        snapshot = parse(context.read_bytes(), str(context))
        result = export(snapshot, Path(args.root), Path(args.output))
    except Exception as error:
        result = {"result": "FAIL", "engineering_authorized": False, "current_permission": False,
                  "diagnostics": [getattr(error, "diagnostic", {"code": "export.unavailable", "message": str(error)})]}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
