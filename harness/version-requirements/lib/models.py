"""固定 Schema 注册表；不解析或下载用户提供的远端 Schema。"""
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from jsonschema.validators import extend

from .core import parse_json, digest
from .errors import CheckError, InputError

HOME = Path(__file__).resolve().parents[1]
SCHEMA_BYTES = (HOME / "schemas/vr.schema.json").read_bytes()
SCHEMA = parse_json(SCHEMA_BYTES)
Draft202012Validator.check_schema(SCHEMA)
SCHEMA_SHA256 = digest(SCHEMA_BYTES)


def _flat_object_uniqueness(validator, enabled, instance, schema):
    """Avoid pairwise comparison for fixed refs; delegate all other shapes.

    Exact string keys/values have the same equality in Python and JSON Schema.
    A frozenset preserves object equality regardless of property order. Keep
    numeric/boolean/nested semantics and every failure diagnostic in the
    pinned library; this invocation owns its set, never a cached verdict.
    """
    if enabled and type(instance) is list and len(instance) > 1:
        seen = set()
        for item in instance:
            if type(item) is not dict or any(type(k) is not str or type(v) is not str
                                             for k, v in item.items()):
                break
            seen.add(frozenset(item.items()))
        else:
            if len(seen) == len(instance):
                return
    yield from Draft202012Validator.VALIDATORS['uniqueItems'](validator, enabled, instance, schema)


SchemaValidator = extend(Draft202012Validator, {'uniqueItems': _flat_object_uniqueness})


def validate(kind, value, *, location="input"):
    if kind not in SCHEMA["$defs"]:
        raise InputError("schema.unsupported", "unknown model: " + kind, refs=[location])
    definition = SCHEMA["$defs"][kind]
    if "schema_version" in definition.get("properties", {}) and isinstance(value, dict):
        version = definition["properties"]["schema_version"]
        supported = version.get("enum", [version.get("const", "vr/1")])
        if "schema_version" in value and value["schema_version"] not in supported:
            raise InputError("schema.unsupported", "unsupported schema_version", refs=[location])
    validator = SchemaValidator({"$ref": "#/$defs/" + kind, "$defs": SCHEMA["$defs"]})
    errors = sorted(validator.iter_errors(value), key=lambda e: (list(map(str, e.absolute_path)), e.message))
    if errors:
        details = ["/" + "/".join(str(x).replace("~", "~0").replace("/", "~1") for x in e.absolute_path)
                   + ": " + e.message for e in errors[:30]]
        raise CheckError("schema." + kind, "\n".join(details), refs=[location])
    return value


def unique(rows, key, *, location):
    result = {}
    for row in rows:
        identity = row[key]
        if identity in result:
            raise CheckError("identity.duplicate", "duplicate " + key + ": " + str(identity), refs=[location])
        result[identity] = row
    return result


def check_requirement_ids(values, *, seen=None):
    """Reject decimal UID aliases without rewriting IDs or conflating revisions.

    Doorstop and the reservation protocol identify the numeric portion by value.
    Keep the originally recorded spelling; different padding cannot create a new R.
    The optional map belongs only to this read-only query's selected closure.
    """
    seen = {} if seen is None else seen
    for uid in values:
        if not isinstance(uid, str) or not re.fullmatch(r'R-[0-9]{3,}', uid):
            raise InputError('requirement.uid', 'invalid Requirement ID', refs=[uid])
        number = uid[2:].lstrip('0') or '0'
        previous = seen.setdefault(number, uid)
        if previous != uid:
            raise CheckError('identity.uid-alias', 'different spellings refer to the same Requirement number',
                             refs=[previous, uid])
    return seen


def scope_requirement_ids(scope):
    """Read named R identities; a source-only exclusion allocates no R ID."""
    names = {row['requirement'] for row in scope['included'] + scope['context_requirements']}
    for row in scope['excluded']:
        for key in ('requirement', 'predecessor'):
            value = row.get(key)
            if value is not None:
                names.add(value if isinstance(value, str) else value['requirement'])
    check_requirement_ids(sorted(names))
    return names
