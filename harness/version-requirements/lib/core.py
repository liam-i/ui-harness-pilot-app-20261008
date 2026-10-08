"""安全数据读取与字节身份；不生成或修复权威记录。"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath

import yaml

from .errors import InputError

MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64


def digest(data):
    return hashlib.sha256(data).hexdigest()


class UniqueLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        self._vr_depth = getattr(self, "_vr_depth", 0) + 1
        if self._vr_depth > MAX_DEPTH:
            raise yaml.constructor.ConstructorError(None, None, "YAML nesting limit exceeded", None)
        try:
            return super().compose_node(parent, index)
        finally:
            self._vr_depth -= 1


def unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise yaml.constructor.ConstructorError(None, None, "duplicate or non-string mapping key",
                                                     key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def json_value(value, depth=0, budget=None):
    if budget is None:
        budget = [1_000_000]
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError("expanded data exceeds one million nodes")
    if depth > MAX_DEPTH:
        raise ValueError("data nesting limit exceeded")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for child in value:
            json_value(child, depth + 1, budget)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for child in value.values():
            json_value(child, depth + 1, budget)
        return
    raise ValueError("only JSON-compatible data is supported; quote dates and timestamps")


def parse_yaml(data):
    """UTF-8 原字节仅用于解析；摘要总是对未转换的输入计算。"""
    try:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError("document exceeds 16 MiB; split structured records")
        value = yaml.load(raw.decode("utf-8-sig"), Loader=UniqueLoader)
        json_value(value)
        return value
    except (UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError) as error:
        raise InputError("input.yaml", str(error)) from error


def parse_json(data):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    try:
        if len(data) > MAX_DOCUMENT_BYTES:
            raise ValueError("document exceeds 16 MiB")
        value = json.loads(data, object_pairs_hook=pairs)
        json_value(value)
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise InputError("input.json", str(error)) from error


def canonical_bytes(value):
    json_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or any(ord(c) < 32 for c in value):
        raise InputError("input.path", "invalid repository-relative path", refs=[str(value)])
    path = PurePosixPath(value)
    if path.is_absolute() or any(x in ("", ".", "..") for x in value.split("/")) or ".git" in path.parts:
        raise InputError("input.path", "non-canonical or reserved path", refs=[value])
    return path


def local_file(root, relative):
    """显式本地缓存/模板读取，不跟随任意一级符号链接。"""
    relative_path(relative)
    root = Path(root)
    if root.is_symlink():
        raise InputError("input.symlink", "root is a symlink", refs=[str(root)])
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.is_symlink():
            raise InputError("input.symlink", "path contains a symlink", refs=[str(current)])
    if not current.is_file():
        raise InputError("input.file", "regular file required", refs=[str(current)])
    return current


def read_yaml(path):
    path = Path(path)
    try:
        return parse_yaml(local_file(path.parent, path.name).read_bytes())
    except OSError as error:
        raise InputError("input.file", str(error), refs=[str(path)]) from error


def snapshot(path, *, times=False):
    path = Path(path)
    if path.is_symlink():
        raise InputError("input.symlink", "root is a symlink")
    result = {}
    for p in sorted(path.rglob("*")):
        relative = p.relative_to(path)
        if ".git" in relative.parts:
            continue
        if p.is_symlink():
            raise InputError("input.symlink", "snapshot contains a symlink", refs=[relative.as_posix()])
        if p.is_file():
            value = {"sha256": digest(p.read_bytes())}
            if times:
                value["mtime_ns"] = p.stat().st_mtime_ns
            result[relative.as_posix()] = value
    return result
