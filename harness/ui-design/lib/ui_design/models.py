"""JSON-compatible YAML, no duplicate keys, aliases, merge keys or coercion."""
from copy import deepcopy
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker
import yaml

from .errors import CheckError, require

TOOL = Path(__file__).resolve().parents[2]
MAX_DOCUMENT = 8 * 1024 * 1024


class Loader(yaml.SafeLoader):
    yaml_implicit_resolvers = deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)


for first, resolvers in Loader.yaml_implicit_resolvers.items():
    Loader.yaml_implicit_resolvers[first] = [
        (tag, pattern) for tag, pattern in resolvers
        if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")
    ]
Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))


def mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        require(isinstance(key, str) and key != "<<" and key not in result,
                "parse.duplicate-key", "keys must be unique strings; merge keys are forbidden",
                location=str(key_node.start_mark))
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


Loader.add_constructor("tag:yaml.org,2002:map", mapping)


def parse(data, source):
    require(len(data) <= MAX_DOCUMENT, "parse.size", "structured document exceeds 8 MiB", source)
    try:
        text = data.decode("utf-8")
        for token in yaml.scan(text):
            require(not isinstance(token, (yaml.AliasToken, yaml.AnchorToken, yaml.TagToken)),
                    "parse.feature", "YAML anchors, aliases and explicit tags are forbidden", source)
        document = yaml.load(text, Loader=Loader)
        json.dumps(document, allow_nan=False)
        return document
    except CheckError as error:
        error.diagnostic["source"] = str(source)
        raise
    except (UnicodeError, yaml.YAMLError, ValueError, TypeError, RecursionError) as error:
        raise CheckError("parse.invalid", str(error), source) from error


def validate(kind, document, source):
    schema = json.loads((TOOL / "schemas/ui.schema.json").read_text())
    require(kind in schema["$defs"], "schema.kind", "unsupported document kind", source)
    model = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{kind}"}
    validator = Draft202012Validator(model, format_checker=FormatChecker())
    error = next(validator.iter_errors(document), None)
    if error:
        detail = "; ".join(e.message for e in error.context[:3])
        raise CheckError("schema.invalid", error.message + ("; " + detail if detail else ""),
                         source, "/" + "/".join(map(str, error.absolute_path)))
    return document
