"""Explicit CI preparation for the original requirement Gate, not a UI gate.

Run only from the reviewed tool checkout. Restore configured full Git stores,
remap physical locators, and preserve the original request. Never select a new
authority revision, change a fixed reference, create an approval, or fetch media.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def source_url(value):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError('UI source must be an explicit credential-free URL or absolute local path')
    if Path(value).is_absolute():
        return value
    if any(c.isspace() for c in value):
        raise ValueError('Encode spaces in the reviewed source URL')
    parsed = urlsplit(value)
    if (parsed.scheme not in ('https', 'ssh', 'file') or parsed.password or
            (parsed.scheme == 'https' and parsed.username) or parsed.query or parsed.fragment or
            (parsed.scheme != 'file' and not parsed.hostname) or
            (parsed.scheme == 'file' and parsed.netloc not in ('', 'localhost'))):
        raise ValueError('Use a reviewed HTTPS/SSH/file source without embedded credentials')
    return value


def prepare(trusted, output, area, sources):
    trusted = trusted.resolve(strict=True)
    output = output.resolve(strict=True)
    area = area.resolve()
    if Path(__file__).resolve() != trusted / 'harness/ui-design/ci/prepare_requirements.py':
        raise ValueError('Run the helper installed in the reviewed trusted checkout')
    if area == trusted or area.is_relative_to(trusted) or area.exists():
        raise ValueError('Use a new UI object directory outside the trusted checkout')
    destinations = [output / 'ui-context.json', output / 'ui-preparation.json']
    if any(p.exists() or p.is_symlink() for p in destinations):
        raise ValueError('Preserve the previous UI preparation and use a new run')
    raw = (output / 'context.json').read_bytes()
    context = json.loads(raw, object_pairs_hook=unique)
    workspace = json.loads((output / 'workspace.json').read_bytes(), object_pairs_hook=unique)
    if (workspace['exit_code'] != 0 or workspace['head_revision'] != context['head_revision'] or
            Path(workspace['trusted_root']).resolve() != trusted or
            context['evaluation_mode'] != 'current'):
        raise ValueError('Expected the prepared current business workspace and original request')
    if not isinstance(sources, dict) or any(not isinstance(key, str) or not key for key in sources):
        raise ValueError('UI sources must map stable repository identities to reviewed sources')
    if 'project' in sources:
        raise ValueError('The project identity belongs to the actual checked business workspace')
    sources = {key: source_url(value) for key, value in sources.items()}
    # Use the same interpreter as scripts/requirements-check. UI_DESIGN_PYTHON
    # cannot repair missing dependencies in this environment.
    sys.path.insert(0, str(trusted / 'harness/version-requirements'))
    from lib.runtime import preflight
    from lib.errors import CheckError
    try:
        runtime = preflight(ui=True)
    except CheckError as error:
        raise ValueError('Joint runtime preflight failed: ' + json.dumps(error.diagnostic())) from None
    prepared = deepcopy(context)
    ui = prepared.get('ui')
    if ui is not None:
        if not isinstance(ui, dict) or not isinstance(ui.get('repositories'), dict):
            raise ValueError('Expected original UI recovery mappings')
        if set(ui['repositories']) - {'project'} != set(sources):
            raise ValueError('Reviewed UI sources must exactly cover the requested foreign repositories')
        # External media are explicitly restored by the host before this step.
        # The original Gate verifies their URI/version/hash and complete bytes.
        for item in ui.get('external_files', []):
            if not Path(item['path']).is_absolute() or not Path(item['path']).is_file():
                raise ValueError('Restore each fixed external media file to an absolute host path first')
    # Keep one reviewed source configuration across stages. Requests without UI
    # input need no UI objects; the original Gate decides whether that is valid.
    # Joint runtime preflight above still applies to every enabled request.
    recovery_sources = sources if ui is not None else {}
    area.mkdir(parents=True, exist_ok=False)
    repositories = {}
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1',
               GIT_NO_LAZY_FETCH='1', GIT_SSH_COMMAND='ssh -oBatchMode=yes -oStrictHostKeyChecking=yes')
    for index, (identity, source) in enumerate(sorted(recovery_sources.items())):
        path = area / f'repository-{index}.git'
        # Mirror all retained refs without a worktree, checkout, filters or hooks.
        # --no-local makes local trials independent too (no borrowed objects).
        subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--mirror', '--no-local',
                        '--', source, str(path)], check=True, timeout=180, env=env)
        repositories[identity] = str(path)
    if ui is not None:
        ui['repositories'] = {**repositories, 'project': workspace['checked_root']}
    # This strict parse precedes reserialization, so duplicate keys cannot be
    # normalized away. Only physical repository locators differ from the raw input.
    encoded = (json.dumps(prepared, ensure_ascii=False, indent=2) + '\n').encode()
    destinations[0].write_bytes(encoded)
    destinations[1].write_text(json.dumps({
        'scope': 'CI recovery only; original Gate still checks all fixed and current inputs',
        'original_sha256': hashlib.sha256(raw).hexdigest(),
        'prepared_sha256': hashlib.sha256(encoded).hexdigest(),
        'repositories': repositories, 'ui_implementation': runtime['ui_implementation'],
    }, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trusted-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repositories-directory', type=Path, required=True)
    args = parser.parse_args()
    try:
        sources = json.loads(os.environ['VR_UI_REPOSITORIES_JSON'], object_pairs_hook=unique)
        prepare(args.trusted_root, args.output, args.repositories_directory, sources)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('UI CI preparation refused: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
