#!/usr/bin/env python3
"""Thin Cocos Android CI entry; approval and current UI checks stay upstream.

Build/test commands belong to the reviewed project. This entry verifies the
host SHA, fixed tool files, actual artifacts, exact cases and cleanup results.
It installs nothing, retries nothing and never signs a human approval.
"""
import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time


def require(condition, message):
    if not condition:
        raise ValueError(message)


def duration(row, limit):
    start, end = row.get("started_at"), row.get("finished_at")
    require(all(type(v) in (int, float) and math.isfinite(v) for v in (start, end)), "missing completion time")
    require(0 <= end - start <= limit, "required work exceeded its reviewed timeout")


def verify_native(build, runtime, expected, head):
    try:
        devices, cases = expected["devices"], expected["cases"]
        names, ids = [d["name"] for d in devices], [c["id"] for c in cases]
        require(len(names) > 0 and len(names) == len(set(names)) == expected["device_count"], "invalid device denominator")
        require(len(ids) > 0 and len(ids) == len(set(ids)) == expected["device_test_count"], "invalid case denominator")
        total = len(names) * len(ids)
        require(total == expected["total_required_device_tests"], "inconsistent independent denominator")
        require(build["passed"] is True and build["source_head"] == head and build["source_dirty"] == "", "build/source identity failed")
        limits = expected["timeouts_seconds"]
        steps = build["steps"]
        require([s["name"] for s in steps] == ["creator", "native"], "missing or duplicate build step")
        for step, code, limit in zip(steps, [36, 0], [limits["creator_export"], limits["native_build"]]):
            require(step["exit"] == code and step["timeout_seconds"] == limit and not step.get("timed_out")
                    and not step.get("interrupted"), "unsuccessful required build step")
            duration(step, limit)
        duration(build, sum([limits["creator_export"], limits["native_build"]]) + 120)
        require(runtime["passed"] is True and runtime["cleanup_errors"] == [], "runtime/cleanup unsuccessful")
        require(runtime["expected_cases"] == total and runtime["apk"] == build["apk"], "runtime build identity differs")
        require(runtime["started_at"] >= build["finished_at"] and runtime["finished_at"] >= runtime["started_at"], "stale/unfinished runtime")
        require([d["name"] for d in runtime["devices"]] == names, "missing, wrong or duplicate device")
        for d, contract in zip(runtime["devices"], devices):
            image = expected["runtime"]
            require(d["identity"] == {"fingerprint": image["fingerprint"], "api": str(image["api"]),
                "abi": image["abi"], "page_size": str(image["page_size"]),
                "size": f"Physical size: {contract['px'][0]}x{contract['px'][1]}",
                "density": f"Physical density: {contract['density']}"}, "device identity differs")
            require(0 <= d["boot_completed_at"] - d["boot_started_at"] <= limits["emulator_boot_per_device"], "device boot timeout")
            require([c["id"] for c in d["cases"]] == ids, "missing, duplicate or unexpected case")
            last = d["boot_completed_at"]
            for c in d["cases"]:
                require(c["status"] == "passed" and c["started_at"] >= last, "case not executed successfully")
                duration(c, limits["case"])
                last = c["finished_at"]
            require(last - d["cases"][0]["started_at"] <= limits["suite_per_device"], "suite timeout")
            require(last <= runtime["finished_at"], "runtime ended before required cases")
        return {"passed": True, "device_count": len(names), "case_count": total}
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("incomplete native result: " + str(error)) from error


def run_command(command, root, output, name, timeout):
    result = {"command": command, "started_at": time.time(), "timeout_seconds": timeout, "interrupted": False}
    try:
        with (output / (name + ".stdout")).open("wb") as so, (output / (name + ".stderr")).open("wb") as se:
            child = subprocess.Popen(command, cwd=root, stdout=so, stderr=se, start_new_session=True)
            try:
                child.wait(timeout=timeout)
            except BaseException:
                result["interrupted"] = True
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=90)  # Project helpers restore owned settings/devices in finally.
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait()
                raise
            finally:
                result["exit"] = child.returncode
    finally:
        result["finished_at"] = time.time()
        (output / (name + ".command.json")).write_text(json.dumps(result, indent=2) + "\n")
    require(result["exit"] == 0 and not result["interrupted"], name + " failed; see retained logs")
    return result


def fingerprint(path):
    return sha256(path.read_bytes()).hexdigest()


def project_file(root, value):
    path = (root / value).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file(), "project file must be inside checkout")
    return path


def verify_artifacts(root, output, build, runtime, expected):
    apk = Path(build["apk"]["path"]).resolve(strict=True)
    require(apk.is_relative_to(output / "build") and apk.stat().st_size == build["apk"]["bytes"]
            and fingerprint(apk) == build["apk"]["sha256"], "actual retained APK differs")
    scene = json.loads((root / "assets/scenes/Menu.scene.meta").read_text())["uuid"]
    require(scene == build["scene_uuid"], "built scene differs")
    for d in runtime["devices"]:
        folder = (output / "runtime" / d["serial"]).resolve(strict=True)
        require(folder.is_relative_to(output / "runtime"), "invalid device evidence path")
        detail = json.loads((folder / "cases.json").read_text())
        require(detail["cases"] == d["cases"], "case detail differs from aggregate")
        shots = detail["screenshots"]
        for case in ["C14", "C15"]:
            required = {s.replace("/", "-") for s in expected["required_states"]}
            required |= {"dialog-reset-empty-zero", "dialog-reset-resumable-zero"}
            got = set()
            for shot in [s for s in shots if s["case"] == case]:
                file = project_file(folder, shot["path"])
                require(fingerprint(file) == shot["sha256"] and file.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "screenshot missing/changed")
                prefix = "C14-" if case == "C14" else "C15-font130-"
                if file.name.startswith(prefix): got.add(file.stem[len(prefix):])
            require(required <= got, "required state screenshot missing")
        require((folder / "commands.json").is_file() and (folder / "logcat.txt").is_file(), "raw device evidence missing")


def execute(root, config_path, host_path, head, output):
    root, output = root.resolve(strict=True), output.resolve()
    require(not output.exists() and output.parent.is_dir() and not output.is_relative_to(root), "use a new output outside checkout")
    output.mkdir()
    record = {"passed": False, "head": head, "started_at": time.time(), "runner_sha256": fingerprint(Path(__file__))}

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True, timeout=30).strip()

    def clean():
        require(git("rev-parse", "HEAD") == head and not git("status", "--porcelain=v1"), "checkout dirty or host SHA differs")

    def source_files():
        return {name: fingerprint(project_file(root, name)) for name in git("ls-files", "-z").split("\0") if name}

    try:
        require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head), "independent exact host SHA required")
        clean()
        require(platform.system() == "Darwin" and platform.machine() == "arm64", "reviewed macOS ARM64 host required")
        config = json.loads(project_file(root, config_path).read_text())
        require(set(config) == {"expected_path", "expected_sha256", "build_script", "test_script", "toolchain_files"}, "unexpected configuration fields")
        require(not host_path.resolve(strict=True).is_relative_to(root), "host paths must be outside repository")
        host = json.loads(host_path.read_text())
        expected_file = project_file(root, config["expected_path"])
        require(fingerprint(expected_file) == config["expected_sha256"], "independent expectation identity differs")
        expected = json.loads(expected_file.read_text())
        require(bool(config["toolchain_files"]), "fixed toolchain identities required")
        tools = []
        for item in config["toolchain_files"]:
            path = Path(host[item["base"]]) / item["relative"] if item["relative"] else Path(host[item["base"]])
            actual = fingerprint(path.resolve(strict=True))
            require(actual == item["sha256"], "toolchain file differs: " + item["base"] + "/" + item["relative"])
            tools.append({**item, "actual_sha256": actual})
        record.update(config=config, toolchain_files=tools, source_files=source_files())
        limits = expected["timeouts_seconds"]
        build_timeout = limits["creator_export"] + limits["native_build"] + 120
        run_timeout = expected["device_count"] * (limits["emulator_boot_per_device"] + limits["suite_per_device"] + 90) + 90
        record["build_command"] = run_command([sys.executable, "-B", str(project_file(root, config["build_script"])),
            "--config", str(host_path), "--output", str(output / "build")], root, output, "build", build_timeout)
        record["runtime_command"] = run_command([sys.executable, "-B", str(project_file(root, config["test_script"])),
            "--config", str(host_path), "--build", str(output / "build/result.json"),
            "--output", str(output / "runtime")], root, output, "runtime", run_timeout)
        build = json.loads((output / "build/result.json").read_text())
        runtime = json.loads((output / "runtime/result.json").read_text())
        verified = verify_native(build, runtime, expected, head)
        verify_artifacts(root, output, build, runtime, expected)
        clean()
        require(record["source_files"] == source_files(), "tracked source changed during native execution")
        record.update(verified=verified, apk=build["apk"], passed=True)
    except Exception as error:
        record["error"] = str(error)
    finally:
        record["finished_at"] = time.time()
        (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--host-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def interrupted(number, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise InterruptedError("native CI interrupted by signal " + str(number))

    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    try:
        result = execute(args.root, args.config, args.host_config, args.head, args.output)
        print(json.dumps({"passed": result["passed"], "error": result.get("error"), "output": str(args.output)}))
        return 0 if result["passed"] else 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
