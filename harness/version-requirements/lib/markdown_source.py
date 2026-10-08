"""固定 Markdown 解析器的来源元数据适配；语法判断仍交给原解析规则。"""
from __future__ import annotations

from pathlib import PurePosixPath
import posixpath
import re
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.rules_block import reference as reference_rule
from markdown_it.rules_inline import autolink as autolink_rule, image as image_rule, link as link_rule

from .core import digest
from .errors import InputError

DIALECT = "commonmark-tables-harness-headings-v1"


def raw_lines(data):
    """与 CommonMark 换行一致，同时保留 CRLF/CR/LF 原字节用于摘要。"""
    lines = re.findall(rb"[^\r\n]*(?:\r\n|\r|\n|$)", data)
    return lines[:-1] if lines and lines[-1] == b"" else lines


def parser():
    md = MarkdownIt("commonmark", {"store_labels": True}).enable("table")
    # Each instance owns its adapter. No mutation of the installed package/helpers module.
    md.helpers = SimpleNamespace(**vars(md.helpers))
    destination = md.helpers.parseLinkDestination
    frames = []

    def located_destination(source, start, maximum):
        result = destination(source, start, maximum)
        if result.ok and frames:
            frames[-1].append({"raw_target": source[start:result.pos], "parsed_target": result.str})
        return result

    md.helpers.parseLinkDestination = located_destination

    def located_reference(state, start_line, end_line, silent):
        frame = []
        frames.append(frame)
        try:
            result = reference_rule(state, start_line, end_line, silent)
        finally:
            frames.pop()
        if result and not silent and frame:
            for reference in state.env.get("references", {}).values():
                if reference.get("map", [None])[0] == start_line:
                    reference["raw_target"] = frame[0]["raw_target"]
        return result

    md.block.ruler.at("reference", located_reference)

    def located_inline(rule, token_type):
        def run(state, silent):
            start, count = state.pos, len(state.tokens)
            frame = []
            frames.append(frame)
            try:
                result = rule(state, silent)
            finally:
                frames.pop()
            if result and not silent:
                token = next(t for t in state.tokens[count:] if t.type == token_type)
                label = token.meta.get("label")
                definition = state.env.get("references", {}).get(label, {}) if label else {}
                token.meta.update(source_syntax=state.src[start:state.pos], inline_start=start,
                                  inline_end=state.pos, inline_prefix=state.src[:start],
                                  raw_target=definition.get("raw_target") if label else (frame[0]["raw_target"] if frame else None),
                                  definition_lines=definition.get("map"))
            return result
        return run

    md.inline.ruler.at("link", located_inline(link_rule, "link_open"))
    md.inline.ruler.at("image", located_inline(image_rule, "image"))
    md.inline.ruler.at("autolink", located_inline(autolink_rule, "link_open"))
    return md


def parse_document(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as error:
        raise InputError("source.encoding", "Markdown must be UTF-8; retain original and provide a reviewed conversion") from error
    if b"\x00" in data:
        raise InputError("source.encoding", "NUL in Markdown requires explicit source repair/conversion")
    md, env = parser(), {}
    tokens = md.parse(text, env)
    lines = raw_lines(data)
    headings, used, links, unsupported, blocks = [], set(), [], [], []
    heading_path = []
    for index, token in enumerate(tokens):
        if token.map:
            start, end = token.map
            blocks.append({"kind": token.type, "start": start + 1, "end": end,
                           "sha256": digest(b"".join(lines[start:end]))})
        if token.type == "heading_open":
            title = "".join(t.content for t in (tokens[index + 1].children or []) if t.type in ("text", "code_inline", "image"))
            base = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-") or "section"
            slug, suffix = base, 0
            while slug in used:
                suffix += 1
                slug = base + "-" + str(suffix)
            used.add(slug)
            level = int(token.tag[1:])
            heading_path = [h for h in heading_path if h["level"] < level]
            heading_path.append({"level": level, "title": title})
            headings.append({"anchor": slug, "title": title, "level": level, "start": token.map[0] + 1,
                             "end": token.map[1], "heading_path": [h["title"] for h in heading_path]})
        if token.type == "html_block":
            unsupported.append({"start": token.map[0] + 1, "end": token.map[1], "syntax": token.content, "reason": "html"})
        if token.type != "inline":
            continue
        for child in token.children or []:
            if child.type in ("link_open", "image"):
                meta = child.meta
                href = child.attrGet("href" if child.type == "link_open" else "src")
                syntax = meta.get("source_syntax", token.content)
                start = token.map[0] + 1 + meta.get("inline_prefix", "").count("\n")
                end = min(token.map[1], start + syntax.count("\n"))
                excerpt = b"".join(lines[start - 1:end]).decode("utf-8-sig")
                definition_lines = meta.get("definition_lines")
                definition_excerpt = (b"".join(lines[slice(*definition_lines)]).decode("utf-8-sig")
                                      if definition_lines else None)
                destination = meta.get("raw_target")
                if child.markup == "autolink":
                    destination = syntax[1:-1]
                # Table rules may consume escaped pipes before inline parsing. Preserve exact
                # original lines even when no standalone destination substring can be recovered.
                original = definition_excerpt if definition_excerpt is not None else excerpt
                if destination is not None and destination not in original:
                    destination = None
                links.append({"kind": "image" if child.type == "image" else "link", "start": start,
                              "end": end, "source_syntax": syntax, "source_excerpt": excerpt,
                              "raw_target": destination, "parsed_target": href,
                              "reference_label": meta.get("label"), "definition_lines": definition_lines,
                              "definition_excerpt": definition_excerpt,
                              "heading_path": [h["title"] for h in heading_path]})
            elif child.type == "html_inline" or (child.type == "text" and "[[" in child.content and "]]" in child.content):
                unsupported.append({"start": token.map[0] + 1, "end": token.map[1], "syntax": child.content,
                                    "reason": "html" if child.type == "html_inline" else "wiki-link"})
    for index, heading in enumerate(headings):
        level = heading["level"]
        heading["section_end"] = next((h["start"] - 1 for h in headings[index + 1:] if h["level"] <= level), len(lines))
    return {"dialect": DIALECT, "sha256": digest(data), "line_count": len(lines), "headings": headings,
            "links": links, "unsupported": unsupported, "blocks": blocks,
            "reference_definitions": env.get("references", {}), "duplicate_references": env.get("duplicate_refs", [])}


def resolve_link(document_path, target, files, documents):
    """只在显式包边界里定位；返回状态，不读取包外路径或下载 URL。"""
    try:
        url = urlsplit(target)
        if url.scheme or url.netloc or target.startswith(("/", "\\")):
            return {"status": "external", "path": None, "anchor": None}
        decoded = unquote(url.path, errors="strict")
        anchor = unquote(url.fragment, errors="strict")
    except (ValueError, UnicodeError):
        return {"status": "unsupported", "path": None, "anchor": None}
    if "\\" in decoded or any(ord(c) < 32 for c in decoded) or url.query:
        return {"status": "unsupported", "path": None, "anchor": anchor or None}
    path = posixpath.normpath(posixpath.join(str(PurePosixPath(document_path).parent), decoded)) if decoded else document_path
    if path == ".." or path.startswith("../") or path.startswith("/"):
        return {"status": "external", "path": None, "anchor": anchor or None}
    if path not in files:
        return {"status": "missing", "path": path, "anchor": anchor or None}
    if anchor:
        if path not in documents:
            return {"status": "unsupported", "path": path, "anchor": anchor}
        candidates = [h for h in documents[path]["headings"] if h["anchor"] == anchor]
        if len(candidates) != 1:
            return {"status": "missing", "path": path, "anchor": anchor}
        return {"status": "resolved", "path": path, "anchor": anchor,
                "selector": {"kind": "lines", "description": candidates[0]["title"],
                             "start": candidates[0]["start"], "end": candidates[0]["section_end"]}}
    return {"status": "resolved", "path": path, "anchor": None}
