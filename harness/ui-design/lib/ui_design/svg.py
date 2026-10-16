"""Validate a passive, self-contained SVG subset without fetching resources."""
import base64
import binascii
import re
from urllib.parse import unquote_to_bytes
import xml.etree.ElementTree as ET

import tinycss2

from .errors import CheckError, require
from .objects import MAX_BLOB

# Unknown resource-producing constructs fail closed; this is not a renderer.
PURE_FUNCTIONS = frozenset(("var", "calc", "min", "max", "clamp", "rgb", "rgba", "hsl", "hsla",
    "hwb", "lab", "lch", "oklab", "oklch", "color", "color-mix", "light-dark", "format", "tech",
    "matrix", "matrix3d", "translate", "translatex", "translatey", "translatez", "translate3d",
    "scale", "scalex", "scaley", "scalez", "scale3d", "rotate", "rotatex", "rotatey", "rotatez",
    "rotate3d", "skew", "skewx", "skewy", "perspective", "blur", "brightness", "contrast",
    "drop-shadow", "grayscale", "hue-rotate", "invert", "opacity", "saturate", "sepia",
    "cubic-bezier", "steps", "linear", "linear-gradient", "radial-gradient", "conic-gradient"))
PASSIVE_AT_RULES = frozenset(("media", "supports", "font-face", "layer", "keyframes", "-webkit-keyframes"))
SVG_NS = "http://www.w3.org/2000/svg"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XLINK_NS = "http://www.w3.org/1999/xlink"

# SVG presentation/geometry attributes carry CSS values; ordinary XML text
# does not. Keep the supported passive subset explicit so an unknown resource
# attribute is not silently accepted as metadata. See SVG 2, Styling 6.6.
CSS_ATTRIBUTES = frozenset("""
    style alignment-baseline baseline-shift clip clip-path clip-rule color
    color-interpolation color-interpolation-filters color-profile color-rendering
    cursor direction display dominant-baseline enable-background fill fill-opacity
    fill-rule filter flood-color flood-opacity font-family font-size font-size-adjust
    font-stretch font-style font-variant font-weight glyph-orientation-horizontal
    glyph-orientation-vertical image-rendering kerning letter-spacing lighting-color
    marker marker-start marker-mid marker-end mask opacity overflow paint-order
    pointer-events shape-rendering stop-color stop-opacity stroke stroke-dasharray
    stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity
    stroke-width text-anchor text-decoration text-overflow text-rendering transform
    transform-origin unicode-bidi vector-effect visibility white-space word-spacing
    writing-mode cx cy d height r rx ry width x y
""".split())
PASSIVE_ATTRIBUTES = frozenset("""
    id class role lang tabindex title version baseprofile contentstyletype
    viewbox preserveaspectratio zoomandpan requiredfeatures requiredextensions
    systemlanguage externalresourcesrequired focusable
    x1 y1 x2 y2 dx dy rotate points pathlength textlength lengthadjust startoffset
    method spacing side path refx refy markerwidth markerheight markerunits orient
    gradientunits gradienttransform spreadmethod fx fy fr offset
    patternunits patterncontentunits patterntransform clippathunits maskunits
    maskcontentunits filterunits primitiveunits filterres in in2 result type values
    mode operator k1 k2 k3 k4 order kernelmatrix divisor bias targetx targety edgemode
    kernelunitlength preservealpha stddeviation radius scale xchannelselector
    ychannelselector basefrequency numoctaves seed stitchtiles surfacescale
    diffuseconstant specularconstant specularexponent limitingconeangle azimuth
    elevation pointsatx pointsaty pointsatz z amplitude exponent intercept slope
    tablevalues media crossorigin decoding
""".split())


def inspect_svg(data, source, depth=0, budget=None):
    require(depth <= 8, "media.external-reference", "embedded SVG nesting exceeds supported depth", source)
    budget = [MAX_BLOB] if budget is None else budget
    budget[0] -= len(data)
    require(budget[0] >= 0, "media.size", "embedded SVG resources exceed supported size", source)

    def resource(value):
        value = value.strip()
        if value.startswith("#") and len(value) > 1:
            return
        require(value.lower().startswith("data:"), "media.external-reference",
                "SVG resources must be embedded; remote or filesystem links are incomplete", source)
        header, separator, body = value[5:].partition(",")
        require(separator, "media.decode", "invalid embedded resource", source)
        fields = header.lower().split(";"); mime = fields[0]
        try:
            raw = unquote_to_bytes(body)
            if fields[-1] == "base64": raw = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error) as error:
            raise CheckError("media.decode", "invalid embedded resource encoding", source) from error
        if mime == "image/svg+xml":
            inspect_svg(raw, source, depth + 1, budget)
        elif mime in ("image/png", "image/jpeg", "image/gif", "image/webp"):
            # Decode, rather than trusting the MIME label of an embedded document.
            from hashlib import sha256
            from io import BytesIO
            from PIL import Image
            from .media import inspect
            try:
                with Image.open(BytesIO(raw)) as image: dimensions = list(image.size)
            except (OSError, ValueError) as error:
                raise CheckError("media.decode", "invalid embedded raster image", source) from error
            inspect(raw, dict(media_type=mime, bytes=len(raw), sha256=sha256(raw).hexdigest(), dimensions_px=dimensions), source)
            budget[0] -= len(raw)
        else:
            require(mime in ("font/woff", "font/woff2", "font/ttf", "font/otf", "application/font-woff",
                             "application/vnd.ms-fontobject"), "media.external-reference",
                    "embedded resource type cannot be proven self-contained", source)
            budget[0] -= len(raw)
        require(budget[0] >= 0, "media.size", "embedded resources exceed supported size", source)

    def css(tokens):
        for token in tokens:
            require(token.type != "error", "media.decode", "unparseable SVG CSS", source)
            if token.type == "at-keyword":
                require(token.lower_value in PASSIVE_AT_RULES, "media.external-reference",
                        "CSS imports and unsupported at-rules cannot enter a fixed SVG", source)
            elif token.type == "url":
                resource(token.value)
            elif token.type == "function":
                if token.lower_name == "url":
                    args = [x for x in token.arguments if x.type not in ("whitespace", "comment")]
                    require(len(args) == 1 and args[0].type == "string", "media.external-reference",
                            "SVG URL must resolve to one fixed literal", source)
                    resource(args[0].value)
                else:
                    require(token.lower_name in PURE_FUNCTIONS, "media.external-reference",
                            "unsupported CSS function cannot be proven self-contained: " + token.lower_name, source)
                    css(token.arguments)
            elif hasattr(token, "content"):
                css(token.content)

    try:
        text = data.decode("utf-8")
        require(not re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b|<\?(?!xml\s)", text, re.I),
                "media.external-reference", "SVG external declarations and processing instructions are unsupported", source)
        xml = ET.fromstring(text)
        require(xml.tag in ("svg", "{" + SVG_NS + "}svg"), "media.decode", "SVG root required", source)
        for node in xml.iter():
            name = node.tag.rsplit("}", 1)[-1].lower()
            require(not node.tag.startswith("{") or node.tag.startswith("{" + SVG_NS + "}"),
                    "media.external-reference", "foreign SVG content is unsupported", source)
            require(name not in ("script", "foreignobject", "animate", "animatetransform", "animatemotion", "set", "discard"),
                    "media.external-reference", "dynamic SVG cannot prove a fixed resource closure", source)
            if name == "style":
                require(node.attrib.get("type", "text/css").lower() == "text/css", "media.external-reference",
                        "unsupported SVG stylesheet type", source)
                css(tinycss2.parse_component_value_list("".join(node.itertext())))
            for attribute, value in node.attrib.items():
                attr = attribute.rsplit("}", 1)[-1].lower()
                namespace = attribute[1:].split("}", 1)[0] if attribute.startswith("{") else ""
                require(attr != "base" and not attr.startswith("on"), "media.external-reference",
                        "SVG base URLs and event handlers are unsupported", source)
                if namespace == XML_NS and attr in ("id", "lang", "space"):
                    continue
                if namespace == XLINK_NS and attr in ("title", "type", "show", "actuate", "role", "arcrole"):
                    continue
                require(not namespace or (namespace == XLINK_NS and attr == "href"),
                        "media.external-reference", "unsupported SVG attribute namespace", source)
                if attr in ("href", "src"):
                    resource(value)
                elif attr in CSS_ATTRIBUTES:
                    css(tinycss2.parse_component_value_list(value))
                else:
                    require(attr in PASSIVE_ATTRIBUTES or attr.startswith(("aria-", "data-")),
                            "media.external-reference", "unsupported SVG attribute: " + attr, source)
    except (UnicodeError, ET.ParseError) as error:
        raise CheckError("media.decode", str(error), source) from error
