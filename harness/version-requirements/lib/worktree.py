"""Read actual Git-visible worktree inputs; optionally retain a new evidence copy.

No source writes, index changes, commits, fetch, publication or test execution.
A captured difference is not a Git commit and does not grant action permission.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

sys.dont_write_bytecode = True
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.core import canonical_bytes, digest, parse_json, relative_path
from lib.errors import CheckError, InputError
from lib.gitstore import GitStore
from lib.models import unique, validate


def _view(path):
    parts = PurePosixPath(path).parts
    return len(parts) >= 4 and parts[:2] == ('requirements', 'versions') and parts[3] == 'views'


def _entry(path, mode, raw):
    return {'path': path, 'mode': mode, 'sha256': digest(raw)}


def _file(root, path):
    relative_path(path)
    parent_fd = None
    try:
        parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        parts = PurePosixPath(path).parts
        for part in parts[:-1]:
            child_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
        name = parts[-1]
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode):
            raw, mode = os.readlink(name, dir_fd=parent_fd).encode('utf-8'), '120000'
        elif stat.S_ISREG(before.st_mode):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            with os.fdopen(descriptor, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise CheckError('worktree.changed', 'file was replaced while reading', refs=[path])
                raw = stream.read()
            mode = '100755' if before.st_mode & 0o111 else '100644'
        else:
            raise InputError('worktree.file-kind', 'only regular files and unfollowed symlink text can be inventoried', refs=[path])
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise InputError('worktree.unreadable', str(error), refs=[path]) from error
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if identity(before) != identity(after):
        raise CheckError('worktree.changed', 'file changed while reading', refs=[path])
    return mode, raw


def _inventory(store, roots):
    paths = set()
    for path in store.git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0'):
        if path:
            try:
                paths.add(path.decode('utf-8'))
            except UnicodeError as error:
                raise InputError('worktree.path-encoding', 'worktree paths must be UTF-8') from error
    # Authority and planning inputs cannot disappear merely through .gitignore.
    # Derived reading views are not authoritative inputs or execution evidence.
    for prefix in roots:
        relative_path(prefix)
        parent = store.root / prefix
        if parent.is_symlink():
            paths.add(prefix)
            continue
        if not parent.exists():
            continue
        if not parent.is_dir():
            paths.add(prefix)
            continue
        for current, directories, files in os.walk(parent, followlinks=False):
            base = Path(current)
            directories[:] = sorted(name for name in directories
                if name != '.git' and not _view((base / name).relative_to(store.root).as_posix()))
            for name in directories + sorted(files):
                path = base / name
                if path.is_symlink() or not path.is_dir():
                    paths.add(path.relative_to(store.root).as_posix())
    return paths


def _index(store):
    result = []
    for raw in store.git('ls-files', '--stage', '-z').split(b'\0'):
        if not raw:
            continue
        metadata, path = raw.split(b'\t', 1)
        mode, oid, stage = metadata.decode('ascii').split()
        if stage != '0':
            raise CheckError('worktree.unmerged', 'resolve the actual index conflict before resuming')
        if mode == '160000':
            raise InputError('worktree.submodule', 'submodule worktree capture requires a separately supported input contract')
        result.append({'path': path.decode('utf-8'), 'mode': mode, 'oid': oid})
    return sorted(result, key=lambda row: row['path'])


def _blob(store, revision, path):
    mode, kind, oid = store.tree(revision)[path]
    if kind != 'blob' or mode not in ('100644', '100755', '120000'):
        raise InputError('worktree.file-kind', 'unsupported fixed input kind', refs=[path])
    # Symlink bytes are evidence of the link itself, never a followed source ref.
    raw = store.read(revision, path) if mode != '120000' else store.git('cat-file', 'blob', oid)
    return mode, raw


def _identity(record):
    return digest(canonical_bytes({key: record[key] for key in ('base_revision', 'extra_roots', 'files')}))


@dataclass
class Worktree:
    record: dict
    contents: dict

    def assert_current(self, store):
        current = capture(store, extra_roots=self.record['extra_roots'])
        if current.record != self.record:
            raise CheckError('worktree.changed', 'HEAD, index or worktree inputs changed during this observation')

    def write(self, store, output):
        output = Path(output).absolute()
        if any(path.is_symlink() for path in [output, *output.parents]):
            raise InputError('worktree.output-path', 'evidence output must not traverse symlinks')
        output = output.resolve()
        if output.exists() or output.is_relative_to(store.root) or not output.parent.is_dir():
            raise CheckError('worktree.output-path', 'choose a new external evidence directory with an existing parent')
        self.assert_current(store)
        output.mkdir()
        # A partial output remains visible on failure; it is never overwritten.
        (output / 'ownership.json').write_text(json.dumps({'purpose': 'worktree-input-evidence',
            'source_root': str(store.root), 'owned': ['worktree.json', 'blobs/']}, indent=2) + '\n')
        (output / 'blobs').mkdir()
        for name, raw in self.contents.items():
            with (output / name).open('xb') as stream:
                stream.write(raw)
        self.assert_current(store)
        with (output / 'worktree.json').open('x') as stream:
            json.dump(self.record, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        return output / 'worktree.json'


def capture(store, *, extra_roots=()):
    roots = sorted(set(extra_roots) | {'requirements'})
    head = store.git('rev-parse', 'HEAD').decode().strip()
    store.commit(head)
    index = _index(store)
    base = store.tree(head)
    paths = _inventory(store, roots) | base.keys()
    files, changes, contents = [], [], {}
    algorithm = hashlib.sha1 if len(head) == 40 else hashlib.sha256
    for path in sorted(paths):
        relative_path(path)
        found = _file(store.root, path)
        old = base.get(path)
        if found is None:
            if old is not None:
                mode, raw = _blob(store, head, path)
                changes.append({'path': path, 'before': _entry(path, mode, raw), 'after': None})
            continue
        mode, raw = found
        current = _entry(path, mode, raw)
        files.append(current)
        oid = algorithm(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if old != (mode, 'blob', oid):
            before = _entry(path, *_blob(store, head, path)) if old is not None else None
            blob = 'blobs/' + current['sha256']
            contents[blob] = raw
            changes.append({'path': path, 'before': before, 'after': {**current, 'blob': blob}})
    retained_index = []
    for row in index:
        blob = None
        if base.get(row['path']) != (row['mode'], 'blob', row['oid']):
            raw = store.git('cat-file', 'blob', row['oid'])
            blob = 'blobs/' + digest(raw)
            contents[blob] = raw
        retained_index.append({**row, 'blob': blob})
    record = {'schema_version': 'vr/1', 'kind': 'worktree-input', 'base_revision': head,
              'extra_roots': roots, 'index_entries': retained_index, 'files': files, 'changes': changes}
    record['input_digest'] = _identity(record)
    validate('worktree_snapshot', record)
    if head != store.git('rev-parse', 'HEAD').decode().strip() or index != _index(store) or paths != (_inventory(store, roots) | base.keys()):
        raise CheckError('worktree.changed', 'HEAD, index or path inventory changed while reading')
    return Worktree(record, contents)


def read_capture(store, reference, *, base_revision):
    """Resolve retained bytes without reading or altering the current worktree."""
    record = validate('worktree_snapshot', parse_json(store.ref(reference)))
    for root in record['extra_roots']:
        relative_path(root)
    if 'requirements' not in record['extra_roots']:
        raise CheckError('worktree.roots', 'capture omitted the required authority namespace')
    if record['base_revision'] != base_revision or record['input_digest'] != _identity(record):
        raise CheckError('worktree.binding', 'capture base or input digest differs from the requested execution')
    store.commit(base_revision)
    files = unique(record['files'], 'path', location='captured worktree files')
    changes = unique(record['changes'], 'path', location='captured worktree differences')
    index = unique(record['index_entries'], 'path', location='captured index')
    actual = {path: _entry(path, *_blob(store, base_revision, path)) for path in store.tree(base_revision)}
    contents = {}
    algorithm = hashlib.sha1 if len(base_revision) == 40 else hashlib.sha256
    for path, row in index.items():
        relative_path(path)
        if row['blob'] is None:
            if store.tree(base_revision).get(path) != (row['mode'], 'blob', row['oid']):
                raise CheckError('worktree.index', 'changed staged content was not retained', refs=[path])
        else:
            if not row['blob'].startswith('blobs/') or len(row['blob']) != len('blobs/') + 64:
                raise CheckError('worktree.index', 'invalid retained staged blob path')
            raw = store.read(reference['commit'], str(PurePosixPath(reference['path']).parent / row['blob']), row['blob'][6:])
            oid = algorithm(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if oid != row['oid']:
                raise CheckError('worktree.index', 'staged object does not match its retained bytes', refs=[path])
    for path, row in changes.items():
        relative_path(path)
        if row['before'] != actual.get(path):
            raise CheckError('worktree.before', 'captured difference does not start at its actual base file', refs=[path])
        after = row['after']
        if after is None:
            if row['before'] is None:
                raise CheckError('worktree.empty-change', 'difference has neither before nor after content')
            actual.pop(path)
        else:
            if after['path'] != path or after['blob'] != 'blobs/' + after['sha256']:
                raise CheckError('worktree.blob-path', 'captured bytes must use their exact local content-addressed path')
            blob_path = str(PurePosixPath(reference['path']).parent / after['blob'])
            ref = {'commit': reference['commit'], 'path': blob_path, 'sha256': after['sha256']}
            raw = store.ref(ref)
            current = _entry(path, after['mode'], raw)
            if current == row['before']:
                raise CheckError('worktree.empty-change', 'unchanged file incorrectly listed as a difference', refs=[path])
            actual[path], contents[path] = current, ref
    if actual != files:
        raise CheckError('worktree.file-set', 'complete captured file inventory disagrees with base plus differences')
    return {'record': record, 'files': files, 'contents': contents, 'reference': reference}


def check_apply_worktree(store, snapshot, observation, *, resuming, extra_roots=()):
    """Bind a current action to actual source files; no historical live reads."""
    from lib.openspec_artifacts import tasks, task_evidence

    root = observation['change_root'].rsplit('/', 1)[0]
    ui_roots = ['harness/ui-design', 'design'] if 'ui' in snapshot else []
    current = capture(store, extra_roots=[root, *ui_roots, *extra_roots])
    if current.record['base_revision'] != snapshot['head_revision']:
        raise CheckError('worktree.head', 'requested head is not the actual worktree HEAD; do not conceal local state with an older snapshot')
    task_path = observation['artifacts']['tasks'][0]
    current_tasks = observation['tasks']
    task_data = store.read(snapshot['head_revision'], task_path)
    fixed = {ref['path'] for ref in observation['input_refs']} | {'scripts/requirements-check'}
    if ui_roots:
        fixed.add('scripts/ui-design-check')
    for row in current.record['changes']:
        path, after = row['path'], row['after']
        if _view(path):
            continue
        if path == task_path:
            if after is None or after['mode'] != row['before']['mode']:
                raise CheckError('worktree.planning-drift', 'actual Tasks are missing or their mode changed')
            task_data = current.contents[after['blob']]
            current_tasks, normalized = tasks(task_data)
            _, approved = tasks(store.read(snapshot['head_revision'], task_path))
            if normalized != approved:
                raise CheckError('worktree.planning-drift', 'uncommitted Task meaning changed; use the actual Update/review path')
            if not resuming:
                raise CheckError('worktree.origin-required', 'changed execution state needs the actual original Apply admission')
            continue
        if (path in fixed or path.startswith(('requirements/', 'harness/version-requirements/', root + '/')) or
                any(path.startswith(p + '/') for p in ui_roots) or
                PurePosixPath(path).name in ('AGENTS.md', '.gitignore', '.gitattributes') or
                path.startswith(('.agents/', '.claude/', '.codex/'))):
            raise CheckError('worktree.fixed-input-changed', 'uncommitted authority, planning or tool input differs from the checked fixed input', refs=[path])
        if not resuming:
            raise CheckError('worktree.origin-required', 'uncommitted implementation cannot be treated as initial admission', refs=[path])
        if any(item is not None and item['mode'] == '120000' for item in (row['before'], after)):
            raise InputError('worktree.changed-symlink', 'changed execution symlinks require a separately qualified input scope', refs=[path])
    _, notes = task_evidence(task_data, store=store)
    current.assert_current(store)
    return {'input': current.record, 'tasks': current_tasks, 'task_evidence': notes,
            'scope': 'actual Git-visible files plus authority/planning roots; execution dependency identities and semantic scope remain separately checked'}


def reviewed_execution_inputs(store, snapshot, observation):
    """Bind post-Apply planning to actual implementation inputs at its Review.

    Version metadata has its own BL/Q/map/Trace/Review checks. Saving that
    metadata must not force committing dirty implementation or recapturing it.
    Historical replay resolves the retained bytes, never today's worktree.
    """
    from lib.openspec_artifacts import tasks, task_evidence

    reference = snapshot.get('planning_inputs_ref')
    if reference is None or snapshot.get('apply_origin_ref') is None:
        raise CheckError('planning.execution-inputs-required', 'post-Apply planning needs the original admission and retained execution inputs')
    record = validate('worktree_snapshot', parse_json(store.ref(reference)))
    selected = read_capture(store, reference, base_revision=record['base_revision'])
    namespace = observation['change_root'].rsplit('/', 1)[0]
    if not any(namespace == root or namespace.startswith(root + '/') for root in record['extra_roots']):
        raise CheckError('planning.execution-roots', 'reviewed capture must include the actual planning namespace even when ignored')
    task_path = observation['artifacts']['tasks'][0]
    def raw(path):
        ref = selected['contents'].get(path)
        return store.ref(ref) if ref else store.read(record['base_revision'], path)
    for ref in observation['input_refs']:
        path = ref['path']
        item = selected['files'].get(path)
        if item is None or item['mode'] != store.tree(ref['commit'])[path][0]:
            raise CheckError('planning.execution-artifact', 'reviewed execution capture omits or changes an observed planning input', refs=[path])
        if path == task_path:
            _, before = tasks(store.ref(ref))
            _, after = tasks(raw(path))
            same = before == after
        else:
            same = item['sha256'] == ref['sha256']
        if not same:
            raise CheckError('planning.execution-artifact', 'reviewed worktree and observed planning content disagree', refs=[path])
    engineering = lambda files: {path: row for path, row in files.items() if not path.startswith('requirements/')}
    expected = engineering(selected['files'])
    if snapshot['evaluation_mode'] == 'current':
        current = check_apply_worktree(store, snapshot, observation, resuming=True, extra_roots=record['extra_roots'])
        actual = engineering({row['path']: row for row in current['input']['files']})
        if expected != actual:
            changed = sorted(path for path in expected.keys() | actual.keys() if expected.get(path) != actual.get(path))
            raise CheckError('planning.execution-inputs-stale', 'implementation inputs changed after the reviewed capture; update the actual Review before planning admission', refs=changed)
    else:
        # Metadata-only saves, including partial commits of captured bytes, are
        # valid. A fixed head containing other engineering bytes is not.
        def fixed(revision):
            return engineering({path: _entry(path, *_blob(store, revision, path)) for path in store.tree(revision)})
        base, head = fixed(record['base_revision']), fixed(snapshot['head_revision'])
        changed = [path for path in base.keys() | expected.keys() | head.keys()
                   if head.get(path) not in (base.get(path), expected.get(path))]
        if changed:
            raise CheckError('planning.execution-inputs-stale', 'fixed planning head contains engineering inputs outside the reviewed capture', refs=sorted(changed))
    selected_tasks, _ = tasks(raw(task_path))
    _, selected_notes = task_evidence(raw(task_path), store=store)
    fixed_task = store.read(snapshot['head_revision'], task_path)
    return {'reference': reference, 'base_revision': record['base_revision'], 'input_digest': record['input_digest'],
            'extra_roots': record['extra_roots'], 'tasks': selected_tasks, 'task_evidence': selected_notes,
            'tasks_revision': snapshot['head_revision'] if digest(fixed_task) == selected['files'][task_path]['sha256'] else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--include-root', action='append', default=[], help='additional source/planning root, including ignored inputs')
    args = parser.parse_args(argv)
    from lib.runtime import preflight
    try:
        preflight()
        store = GitStore(args.root)
        found = capture(store, extra_roots=args.include_root)
        path = found.write(store, args.output)
        print(json.dumps({'result': 'captured', 'path': str(path), 'input_digest': found.record['input_digest'],
                          'base_revision': found.record['base_revision'], 'permission': False}))
        return 0
    except (CheckError, InputError) as error:
        print(json.dumps({'result': 'failed', 'rule_id': error.rule, 'evidence': str(error)}))
        return 2 if isinstance(error, InputError) else 1


if __name__ == '__main__':
    raise SystemExit(main())
