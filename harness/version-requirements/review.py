"""显式封装官方 Doorstop review：只接收原生标记，保留所有原始字段值。"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from lib.backend import STRICT, valid_stamp
from lib.core import digest, local_file, parse_yaml
from lib.errors import CheckError, InputError
from lib.models import check_requirement_ids, validate
from lib.runtime import preflight


def review(root, uid):
    """One already reviewed working item; no approval, Git or history writes.

    Doorstop's native serializer may append newlines to extended scalar fields.
    Native review runs on an owned projection. Its stamp is combined with the
    original values, then native strict checks that exact candidate before any
    project write. Fingerprints and validation remain official Doorstop code.
    """
    preflight()
    check_requirement_ids([uid])
    root = Path(root)
    if root.is_symlink():
        raise InputError('input.symlink', 'root is a symlink')
    root = root.resolve(strict=True)
    path = local_file(root, 'requirements/items/' + uid + '.yml')
    config = local_file(root, 'requirements/items/.doorstop.yml')
    original, configuration = path.read_bytes(), config.read_bytes()
    value = validate('requirement', parse_yaml(original))
    reviewed_fields = parse_yaml(configuration).get('attributes', {}).get('reviewed', [])
    if not ({'retires', 'supersedes'} & value.keys()) <= set(reviewed_fields):
        raise CheckError('review.configuration', 'used retirement/replacement fields must participate in native review')
    env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_') and k not in ('PYTHONPATH','PYTHONHOME')}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0', PYTHONDONTWRITEBYTECODE='1')
    operations = []
    with tempfile.TemporaryDirectory(prefix='vr-native-review-') as temporary:
        stage = Path(temporary)
        items = stage/'requirements/items'; items.mkdir(parents=True)
        staged = items/path.name
        staged.write_bytes(original); (items/'.doorstop.yml').write_bytes(configuration)
        command = [sys.executable, '-I', '-B', str(Path(sys.executable).parent/'doorstop'), '--project', str(stage)]
        for args in (['git', '-c', 'core.hooksPath=/dev/null', 'init', '--quiet', str(stage)],
                     command + ['review', uid]):
            run = subprocess.run(args, cwd=stage, env=env, capture_output=True, timeout=30, check=False)
            operations.append({'command':args,'exit_code':run.returncode,
                'stdout':run.stdout.decode(errors='replace'),'stderr':run.stderr.decode(errors='replace')})
            if run.returncode:
                raise CheckError('review.native', 'native review preparation failed; original item unchanged', refs=operations)
        native = parse_yaml(staged.read_bytes())
        if not valid_stamp(native.get('reviewed')):
            raise CheckError('review.stamp', 'native review did not produce a valid stamp')
        selected = copy.deepcopy(value); selected['reviewed'] = native['reviewed']
        candidate = yaml.safe_dump(selected, allow_unicode=True, sort_keys=False).encode()
        if parse_yaml(candidate) != selected:
            raise InputError('review.serialization', 'candidate serialization changed original field values')
        staged.write_bytes(candidate)
        run = subprocess.run(command + STRICT, cwd=stage, env=env, capture_output=True, timeout=30, check=False)
        operations.append({'command':command + STRICT,'exit_code':run.returncode,
            'stdout':run.stdout.decode(errors='replace'),'stderr':run.stderr.decode(errors='replace')})
        if run.returncode or staged.read_bytes() != candidate:
            raise CheckError('review.strict', 'native strict did not verify the preserved original values; original item unchanged', refs=operations)
    if (local_file(root, 'requirements/items/' + uid + '.yml') != path or
            local_file(root, 'requirements/items/.doorstop.yml') != config or
            path.read_bytes() != original or config.read_bytes() != configuration):
        raise CheckError('review.concurrent-change', 'item/configuration changed during native review; re-read before retrying')
    changed = value.get('reviewed') != selected['reviewed']
    if changed:
        pending = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+uid+'-', suffix='.tmp', delete=False) as output:
                pending = Path(output.name)
                output.write(candidate); output.flush(); os.fsync(output.fileno())
            pending.chmod(path.stat().st_mode & 0o777)
            os.replace(pending, path)
        finally:
            if pending is not None: pending.unlink(missing_ok=True)
    return {'requirement':uid, 'changed':changed, 'before_sha256':digest(original),
        'after_sha256':digest(path.read_bytes()), 'configuration_sha256':digest(configuration),
        'reviewed':selected['reviewed'], 'operations':operations,
        'scope':'official native stamp only; original field values preserved; no product approval, Gate or project Git/index write'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--requirement', required=True)
    args = parser.parse_args()
    try:
        result = review(args.root, args.requirement)
    except (CheckError, InputError) as error:
        print(json.dumps({'result':'failed', **error.diagnostic()}, ensure_ascii=False))
        return 2 if isinstance(error, InputError) else 1
    except (OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'result':'failed','rule_id':'review.operation','message':str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == '__main__': raise SystemExit(main())
