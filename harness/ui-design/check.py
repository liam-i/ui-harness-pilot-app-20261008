#!/usr/bin/env python3
"""Read a fixed snapshot and print JSON. This entry never writes output files."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))


class ArgumentError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError(message)


def main():
    parser = Parser(description="Validate fixed UI inputs, optionally observing declared current UI authority.")
    parser.add_argument("--root", default=".", help="base for explicit local repository/object mappings")
    parser.add_argument("--context", help="JSON or YAML fixed snapshot")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--describe", action="store_true", help="verify installation and print rule identity")
    parser.add_argument("--action", choices=["propose", "start", "resume", "pre-merge", "integrated", "release"],
                        help="require a current snapshot for this original Change/task action; grants no permission")
    try:
        args = parser.parse_args()
        if args.describe and (args.action or args.context):
            parser.error("--describe is installation inspection, not an action/context check")
        from ui_design.api import check
        from ui_design.models import parse
        from ui_design.runtime import identity, implementation, CAPABILITIES
        if args.describe:
            result = dict(result="PASS", rules=identity(), implementation=implementation(), capabilities=list(CAPABILITIES),
                          current_supported=True, engineering_authorized=False, current_permission=False)
        else:
            if not args.context: parser.error("--context is required unless --describe is selected")
            path = Path(args.context)
            context = parse(path.read_bytes(), str(path))
            if args.action:
                if not isinstance(context, dict) or context.get("mode") != "current" or context.get("action") != args.action:
                    parser.error("action entry requires mode=current and the same action in the fixed context")
                if context.get("subject", {}).get("kind") not in ("change", "task"):
                    parser.error("this action entry accepts the original Change/task only; requirement-layer integration is separate")
            result = check(context, Path(args.root))
    except Exception as error:
        # Startup/parse/environment errors must also be JSON and nonzero.
        diagnostic = getattr(error, "diagnostic", dict(code="entry.arguments" if isinstance(error, ArgumentError) else "runtime.unavailable",
                                                      message=str(error), source="entry", location=""))
        result = dict(schema_version="ui-result/1", result="FAIL", mode=None, rules=None, inputs=[], packages=[],
                      engineering_authorized=False, current_permission=False, diagnostics=[diagnostic],
                      proof_scope="no fixed-input verification completed")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
