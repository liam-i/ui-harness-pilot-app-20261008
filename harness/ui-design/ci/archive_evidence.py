#!/usr/bin/env python3
"""Package one finished iOS evidence tree without dereferencing its links.

Upload the tar and its adjacent manifest, rather than the source directory.
Only the native runner's full simulator inventories are excluded. This is a
transport helper; it never changes or decides the native test result.
"""
import argparse
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import tempfile


INVENTORY = re.compile(r"native/device-[0-9]+-before\.stdout")


def identity(value):
    # Reading can change atime; that is not an evidence mutation.
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def inventory(source):
    entries, excluded = {}, []

    def visit(path):
        name = path.relative_to(source).as_posix()
        value = path.lstat()
        if INVENTORY.fullmatch(name):
            if not stat.S_ISREG(value.st_mode):
                raise ValueError("simulator inventory must be a regular file: " + name)
            excluded.append(name)
            return
        link = None
        if stat.S_ISLNK(value.st_mode):
            link = os.readlink(path)
            if Path(link).is_absolute() or not path.resolve().is_relative_to(source):
                raise ValueError("symlink must stay within the evidence tree: " + name)
        elif not (stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode)):
            raise ValueError("unsupported evidence entry: " + name)
        entries[name] = (value, link)
        if stat.S_ISDIR(value.st_mode):
            for child in sorted(path.iterdir()):
                visit(child)

    visit(source)
    return entries, excluded


def fingerprint(entries):
    return {name: (identity(value), link) for name, (value, link) in entries.items()}


class DigestReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = sha256()

    def read(self, size):
        data = self.stream.read(size)
        self.digest.update(data)
        return data


def package(source, output):
    source = source.resolve(strict=True)
    output = output.parent.resolve(strict=True) / output.name
    manifest = output.with_name(output.name + ".manifest.json")
    if not source.is_dir() or output.is_relative_to(source):
        raise ValueError("use an evidence directory and a new output outside it")
    if any(os.path.lexists(path) for path in (output, manifest)):
        raise FileExistsError("archive and manifest must both be new")
    entries, excluded = inventory(source)
    records = []
    published = []
    try:
        with tempfile.TemporaryDirectory(prefix=".ui-evidence-", dir=output.parent) as temporary:
            archive_path = Path(temporary) / "evidence.tar"
            with tarfile.open(archive_path, "w", format=tarfile.PAX_FORMAT) as archive:
                for name, (value, link) in entries.items():
                    path = source / name
                    info = tarfile.TarInfo(name)
                    info.mode = stat.S_IMODE(value.st_mode)
                    info.mtime = value.st_mtime
                    # TarInfo defaults to neutral owner IDs/names. Do not copy
                    # host ownership/ACLs/xattrs or synthesize AppleDouble files.
                    record = {"path": name, "mode": info.mode}
                    if stat.S_ISREG(value.st_mode):
                        info.size = value.st_size
                        # Refuse a last-moment symlink replacement of a file.
                        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                        with os.fdopen(descriptor, "rb") as stream:
                            if identity(os.fstat(stream.fileno())) != identity(value):
                                raise ValueError("evidence changed while packaging: " + name)
                            reader = DigestReader(stream)
                            archive.addfile(info, reader)
                            if identity(os.fstat(stream.fileno())) != identity(value):
                                raise ValueError("evidence changed while packaging: " + name)
                        record.update(kind="file", bytes=info.size, sha256=reader.digest.hexdigest())
                    else:
                        if link is not None:
                            info.type = tarfile.SYMTYPE
                            info.linkname = link
                            record.update(kind="symlink", target=link)
                        else:
                            info.type = tarfile.DIRTYPE
                            record.update(kind="directory")
                        archive.addfile(info)
                    records.append(record)
            after, excluded_after = inventory(source)
            if fingerprint(after) != fingerprint(entries) or excluded_after != excluded:
                raise ValueError("evidence changed while packaging")
            with archive_path.open("rb") as stream:
                digest = file_digest(stream, "sha256").hexdigest()
            result = {"schema_version": 1, "archive": {"name": output.name,
                      "bytes": archive_path.stat().st_size, "sha256": digest},
                      "entries": records, "excluded": excluded}
            manifest_path = Path(temporary) / "manifest.json"
            manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # Hard-link publication refuses concurrent overwrites. Both files
            # are complete before either becomes visible to the upload step.
            for prepared, destination in ((archive_path, output), (manifest_path, manifest)):
                os.link(prepared, destination)
                published.append(destination)
        return result
    except BaseException:
        for path in reversed(published):
            path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package(args.source, args.output)


if __name__ == "__main__":
    main()
