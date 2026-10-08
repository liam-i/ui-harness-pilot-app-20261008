#!/usr/bin/env python3
"""Run reviewed iOS tests on explicitly selected dedicated simulators.

This is a platform runner, not a UI approval or a replacement for Harness Gates.
It installs nothing, uses the existing Xcode selection, and retains failed runs.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def verify_summary(summary, expected):
    counts = {k: summary.get(k) for k in ("totalTestCount", "passedTests", "failedTests", "skippedTests", "expectedFailures")}
    if not isinstance(expected, int) or expected <= 0:
        raise ValueError("expected test count must be an independently reviewed positive number")
    if summary.get("result") != "Passed" or counts != {"totalTestCount": expected, "passedTests": expected,
            "failedTests": 0, "skippedTests": 0, "expectedFailures": 0}:
        raise ValueError("native result differs from reviewed test denominator: " + json.dumps(counts))
    return counts


def execute(root, config, head, output):
    root = root.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(root) or output.exists() or not output.parent.is_dir():
        raise ValueError("use a new output directory outside the project with an existing parent")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise ValueError("host must provide the exact checked commit")
    output.mkdir()
    record = {"started_at": now(), "head": head, "root": str(root), "config": config, "commands": [],
              "devices": [], "passed": False, "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}

    def run(command, name, timeout=60, required=True):
        start = time.monotonic()
        with (output / (name + ".stdout")).open("wb") as so, (output / (name + ".stderr")).open("wb") as se:
            process = subprocess.Popen(command, cwd=root, stdout=so, stderr=se, start_new_session=True)
            timed_out = False
            try:
                process.wait(timeout=timeout)
            except BaseException:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
            finally:
                record["commands"].append({"command": command, "name": name, "timeout_seconds": timeout,
                    "seconds": time.monotonic() - start, "exit_code": process.returncode, "interrupted": timed_out})
        if required and process.returncode != 0:
            raise RuntimeError(name + " failed; see retained stdout/stderr")
        return (output / (name + ".stdout")).read_text(errors="replace")

    def source_manifest():
        result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
        return {name: sha256((root / name).read_bytes()).hexdigest()
                for name in result.stdout.decode().split("\0") if name}

    try:
        actual = run(["git", "rev-parse", "HEAD"], "head-before").strip()
        if actual != head or run(["git", "status", "--porcelain=v1"], "status-before").strip():
            raise ValueError("checked project is dirty or does not match host SHA")
        record["source_files"] = source_manifest()
        if run(["xcodebuild", "-version"], "xcode").strip() != config["xcode_version"]:
            raise ValueError("Xcode differs from reviewed configuration")
        for index, device in enumerate(config["devices"]):
            label = "device-" + str(index)
            state = json.loads(run(["xcrun", "simctl", "list", "devices", "--json"], label + "-before"))
            matches = [(runtime, row) for runtime, rows in state["devices"].items() for row in rows
                       if row["udid"] == device["udid"] and row["name"] == device["name"]]
            if len(matches) != 1 or matches[0][0] != config["runtime"] or not matches[0][1]["isAvailable"] or matches[0][1]["state"] != "Shutdown":
                raise ValueError("dedicated simulator is absent, unavailable, busy or has a different runtime")
            one = {"device": device, "before": matches[0], "passed": False, "cleanup": []}
            record["devices"].append(one)
            booted = False
            appearance = size = None
            try:
                run(["xcrun", "simctl", "boot", device["udid"]], label + "-boot")
                booted = True
                run(["xcrun", "simctl", "bootstatus", device["udid"], "-b"], label + "-bootstatus")
                appearance = run(["xcrun", "simctl", "ui", device["udid"], "appearance"], label + "-appearance-before").strip()
                size = run(["xcrun", "simctl", "ui", device["udid"], "content_size"], label + "-size-before").strip()
                run(["xcrun", "simctl", "ui", device["udid"], "appearance", "light"], label + "-light")
                run(["xcrun", "simctl", "ui", device["udid"], "content_size", "large"], label + "-size-default")
                result_bundle = output / (label + ".xcresult")
                command = ["xcodebuild", "-project", config["project"], "-scheme", config["scheme"],
                    "-sdk", "iphonesimulator", "-destination", "platform=iOS Simulator,id=" + device["udid"],
                    "-configuration", "Debug", "-derivedDataPath", str(output / "derived"),
                    "-resultBundlePath", str(result_bundle), "-disableAutomaticPackageResolution",
                    "-parallel-testing-enabled", "NO", "CODE_SIGNING_ALLOWED=NO", "IPHONEOS_DEPLOYMENT_TARGET=15.0", "test"]
                command += ["-only-testing:" + target for target in config["test_targets"]]
                # A failure/timeout is retained; no automatic retry or test reduction.
                run(command, label + "-xcodebuild", timeout=config["test_timeout_seconds"], required=False)
                xcode_exit = record["commands"][-1]["exit_code"]
                summary = json.loads(run(["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", str(result_bundle)], label + "-summary"))
                run(["xcrun", "xcresulttool", "get", "test-results", "tests", "--path", str(result_bundle)], label + "-tests")
                run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(result_bundle),
                     "--output-path", str(output / (label + "-attachments"))], label + "-attachments")
                if xcode_exit != 0:
                    raise RuntimeError("xcodebuild failed; native result and attachments retained")
                one["counts"] = verify_summary(summary, config["expected_tests"])
                bundle = output / "derived/Build/Products/Debug-iphonesimulator" / config["app_bundle"]
                token = bundle / config["bundled_tokens"]["path"]
                if sha256(token.read_bytes()).hexdigest() != config["bundled_tokens"]["sha256"]:
                    raise ValueError("built tokens differ from approved design")
                one["build_files"] = {p.relative_to(bundle).as_posix(): {"sha256": sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                                      for p in bundle.rglob("*") if p.is_file()}
                one["passed"] = True
            finally:
                if booted:
                    for option, value in [("appearance", appearance), ("content_size", size)]:
                        if value:
                            run(["xcrun", "simctl", "ui", device["udid"], option, value], label + "-restore-" + option, required=False)
                            one["cleanup"].append(record["commands"][-1])
                    run(["xcrun", "simctl", "shutdown", device["udid"]], label + "-shutdown", required=False)
                    one["cleanup"].append(record["commands"][-1])
                    if any(item["exit_code"] != 0 for item in one["cleanup"]):
                        raise RuntimeError("simulator cleanup failed; retained state requires attention")
        if not record["devices"]:
            raise ValueError("no reviewed device selection")
        record["source_unchanged"] = source_manifest() == record["source_files"] and run(["git", "rev-parse", "HEAD"], "head-after").strip() == head
        if not record["source_unchanged"] or run(["git", "status", "--porcelain=v1"], "status-after").strip():
            raise ValueError("source changed during native validation")
        record["passed"] = all(item["passed"] for item in record["devices"])
    except Exception as error:
        record["error"] = str(error)
    finally:
        record["finished_at"] = now()
        (output / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = execute(args.root, json.loads(args.config.read_text()), args.head, args.output)
    print(json.dumps({"passed": result["passed"], "head": result["head"], "devices": len(result["devices"]),
                      "error": result.get("error"), "record": str(args.output / "result.json")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
