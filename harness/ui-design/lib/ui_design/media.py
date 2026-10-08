"""Read bytes and decode supported still images; never execute prototypes."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import warnings
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image, ImageFile

from .errors import CheckError, require
from .models import parse
from .objects import MAX_BLOB


def inspect(data, declaration, source):
    require(not data.startswith(b"version https://git-lfs.github.com/spec/v1"), "media.pointer",
            "an LFS pointer cannot stand in for media bytes", source)
    require(len(data) == declaration["bytes"], "media.size", "byte length differs from declaration", source)
    require(sha256(data).hexdigest() == declaration["sha256"], "object.digest", "media SHA-256 mismatch", source)
    mime = declaration["media_type"]
    if mime in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as im:
                    expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/gif": "GIF", "image/webp": "WEBP"}[mime]
                    require(im.format == expected, "media.type", "declared image type differs from bytes", source)
                    require("dimensions_px" in declaration and list(im.size) == declaration["dimensions_px"],
                            "media.dimensions", "missing or incorrect pixel dimensions", source)
                    im.verify()
                with Image.open(BytesIO(data)) as im:
                    for frame in range(getattr(im, "n_frames", 1)):
                        im.seek(frame); im.load()
        except CheckError:
            raise
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise CheckError("media.decode", str(error), source) from error
    elif mime == "image/svg+xml":
        try:
            text = data.decode("utf-8")
            require("<!DOCTYPE" not in text.upper() and "<!ENTITY" not in text.upper(),
                    "media.decode", "DTD and entity declarations are forbidden", source)
            xml = ET.fromstring(text)
            require(xml.tag.split("}")[-1] == "svg", "media.decode", "SVG root required", source)
            for node in xml.iter():
                for attribute, value in node.attrib.items():
                    if attribute.split("}")[-1] in ("href", "src"):
                        require(value.startswith(("#", "data:")), "media.external-reference",
                                "SVG resources must be embedded; remote or filesystem links are incomplete", source)
        except (UnicodeError, ET.ParseError) as error:
            raise CheckError("media.decode", str(error), source) from error
    elif mime.startswith("image/"):
        raise CheckError("media.unsupported", "image decoder not supported for " + mime, source)
    elif mime in ("application/json", "application/yaml", "text/yaml"):
        parse(data, source)
    elif mime.startswith("text/"):
        try: data.decode("utf-8")
        except UnicodeError as error: raise CheckError("media.decode", "text is not UTF-8", source) from error
    elif mime == "application/zip":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                require(sum(i.file_size for i in archive.infolist()) <= MAX_BLOB, "media.size", "expanded ZIP exceeds limit", source)
                require(archive.testzip() is None, "media.decode", "ZIP CRC failure", source)
        except (zipfile.BadZipFile, RuntimeError, OSError) as error:
            raise CheckError("media.decode", str(error), source) from error
    # Other binary types are checked for fixed bytes, not claimed to be playable/renderable.


def external(declaration, supplied, root):
    matches = [x for x in supplied if (x["uri"], x["version"], x["sha256"]) ==
               (declaration["uri"], declaration["version"], declaration["sha256"])]
    require(len(matches) == 1, "media.external-missing", "supply exactly one restored local object", declaration["id"])
    path = Path(matches[0]["path"])
    path = path if path.is_absolute() else Path(root) / path
    require(path.is_file() and not path.is_symlink(), "media.external-missing", "restored media file missing or symlink", path)
    require(path.stat().st_size <= MAX_BLOB, "media.size", "external object exceeds 128 MiB limit", path)
    data = path.read_bytes()
    inspect(data, declaration, str(path))
    return dict(uri=declaration["uri"], version=declaration["version"], sha256=declaration["sha256"], bytes=len(data))
