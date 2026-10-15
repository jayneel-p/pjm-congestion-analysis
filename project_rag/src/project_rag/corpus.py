"""Parse an explicit, local corpus without executing source content."""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path, PurePosixPath


class RAGError(ValueError):
    """An expected corpus, index or query failure."""


@dataclass
class Block:
    text: str
    section: str
    start: int
    end: int
    anchor: str = ""
    locator: str = ""


CORPUS_PROFILES = ("full", "published")


def default_corpus(profile: str = "full") -> dict:
    if profile not in CORPUS_PROFILES:
        raise RAGError("Corpus profile must be full or published.")
    resource = "corpus_published.json" if profile == "published" else "corpus.json"
    return json.loads(files("project_rag").joinpath(resource).read_text())


def source_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RAGError("Corpus paths must be relative and remain inside the project.")
    if any(part.startswith(".") for part in path.parts):
        raise RAGError("Hidden/runtime files cannot enter the corpus.")
    if any(part in {"raw", "private", "baseline", "prior_evidence"} for part in path.parts):
        raise RAGError("Raw, private and archived inputs are outside this corpus.")
    if path.suffix.lower() not in {".md", ".html", ".tex", ".json", ".csv"}:
        raise RAGError("Only selected text/document sources may enter the corpus.")
    if re.search(r"credential|secret|token|api[-_]key", path.name, re.I):
        raise RAGError("Credential files cannot enter the corpus.")
    candidate = root.joinpath(*path.parts)
    for parent in [candidate, *candidate.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise RAGError(f"Symlink sources are not permitted: {relative}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise RAGError(f"Missing or out-of-project source: {relative}")
    return resolved


def normalized(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def reject_secrets(text: str, path: str) -> None:
    patterns = [
        r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{28,}",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"(?i)(?:PJM_API_KEY|Ocp-Apim-Subscription-Key)\s*[=:]\s*[\"']?[a-f0-9]{32}\b",
    ]
    if any(re.search(pattern, text) for pattern in patterns):
        raise RAGError(f"Possible credential in corpus source; indexing stopped: {path}")


def pack(blocks: list[Block], limit: int) -> list[Block]:
    result: list[Block] = []
    for block in blocks:
        text = normalized(block.text)
        if len(text) < 25:
            continue
        # Split at whitespace, preserving every numeric/source token.
        words = re.findall(r"\S+\s*", text)
        parts, current = [], ""
        for word in words:
            if len(word.rstrip()) > limit:
                raise RAGError("Source contains an oversized text token; review corpus extraction.")
            if current and len(current) + len(word) > limit:
                parts.append(current.rstrip())
                current = ""
            current += word
        if current:
            parts.append(current.rstrip())
        for part in parts:
            if (
                result
                and result[-1].section == block.section
                and (
                    result[-1].anchor == block.anchor
                    and result[-1].locator == block.locator
                    and len(result[-1].text) + len(part) + 2 <= limit
                )
            ):
                result[-1].text += "\n\n" + part
                result[-1].end = max(result[-1].end, block.end)
            else:
                result.append(
                    Block(part, block.section, block.start, block.end, block.anchor, block.locator)
                )
    return result


def markdown(text: str) -> list[Block]:
    headings: dict[int, str] = {}
    blocks, current = [], []
    start = 1
    skip_section = False

    def flush(end):
        if current and not skip_section:
            blocks.append(Block("\n".join(current), " > ".join(headings.values()), start, end))
        current.clear()

    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            flush(number - 1)
            level, title = len(match[1]), match[2].strip()
            headings = {key: value for key, value in headings.items() if key < level}
            headings[level] = title
            if level <= 2:
                skip_section = bool(re.search(r"PJM API MCP|Project knowledge RAG", title, re.I))
            start = number
            current.append(line)
        elif not line.strip():
            flush(number)
            start = number + 1
        else:
            if not current:
                start = number
            current.append(line)
    flush(len(text.splitlines()))
    return blocks


class ReportText(HTMLParser):
    VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    OMIT = {"head", "script", "style", "svg", "canvas", "noscript", "template"}
    BLOCK = {"p", "li", "tr", "figcaption", "blockquote", "pre", "dt", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.blocks = []
        self.words = []
        self.tag = ""
        self.start = 1
        self.headings = {}
        self.anchor = ""
        self.section_anchor = ""
        self.table_header = ""
        self.row_header = False

    @property
    def skipped(self):
        return bool(self.stack and self.stack[-1][1])

    def flush(self):
        text = normalized("".join(self.words))
        if text:
            if re.fullmatch(r"h[1-6]", self.tag):
                level = int(self.tag[1])
                self.headings = {key: value for key, value in self.headings.items() if key < level}
                self.headings[level] = text
            else:
                if self.tag == "tr":
                    if self.row_header:
                        self.table_header = text
                    elif self.table_header:
                        text = self.table_header + "\n" + text
                self.blocks.append(
                    Block(
                        text,
                        " > ".join(self.headings.values()),
                        self.start,
                        self.getpos()[0],
                        self.anchor or self.section_anchor,
                    )
                )
        self.words = []
        self.tag = ""
        self.row_header = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        omit = self.skipped or tag in self.OMIT or "hidden" in attributes
        omit = omit or attributes.get("aria-hidden") == "true"
        omit = omit or bool(re.search(r"display\s*:\s*none", attributes.get("style", "")))
        if tag not in self.VOID:
            self.stack.append((tag, omit))
        if omit:
            return
        if tag == "section" and attributes.get("id"):
            self.section_anchor = attributes["id"]
        if tag == "figure":
            self.flush()
            self.anchor = attributes.get("id", self.section_anchor)
        if tag in self.BLOCK or re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.tag, self.start = tag, self.getpos()[0]
            if attributes.get("id"):
                self.section_anchor = attributes["id"]
        if tag in {"td", "th"}:
            if self.words:
                self.words.append(" | ")
            self.row_header = self.row_header or tag == "th"
        if tag == "br" and self.tag:
            self.words.append("\n")

    def handle_endtag(self, tag):
        if not self.skipped:
            if tag == self.tag:
                self.flush()
            if tag == "figure":
                self.anchor = ""
            if tag == "table":
                self.table_header = ""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        if not self.skipped and self.tag:
            self.words.append(data)


def html(text: str) -> list[Block]:
    parser = ReportText()
    parser.feed(text)
    parser.flush()
    return parser.blocks


def balanced(text: str, offset: int) -> tuple[str, int]:
    if offset >= len(text) or text[offset] != "{":
        raise RAGError("Invalid TeX prose argument.")
    depth = 0
    for index in range(offset, len(text)):
        if index and text[index - 1] == "\\":
            continue
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[offset + 1 : index], index + 1
    raise RAGError("Unclosed TeX prose argument.")


def latex_plain(text: str) -> str:
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\[[^]]*\])?", "\n", text)
    text = text.replace(r"\%", "%").replace(r"\$", "$").replace(r"\&", "&")
    text = re.sub(r"\\(?:par|item|talkhead)\b", "\n", text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^]]*\])?", "", text)
    return text.replace("{", "").replace("}", "").replace(r"\\", "\n")


def latex(text: str, notes_only: bool) -> list[Block]:
    blocks = []
    if notes_only:
        frames = list(re.finditer(r"\\begin\{frame\}(?:\[[^]]*\])?\{([^{}]+)\}", text))
        for note in re.finditer(r"\\note\{", text):
            raw, end = balanced(text, note.end() - 1)
            preceding = [frame for frame in frames if frame.start() < note.start()]
            title = preceding[-1][1] if preceding else "Frame notes"
            blocks.append(
                Block(
                    latex_plain(raw),
                    title,
                    text.count("\n", 0, note.start()) + 1,
                    text.count("\n", 0, end) + 1,
                )
            )
    else:
        for slide in re.finditer(r"\\begin\{slidepage\}", text):
            args, cursor = [], slide.end()
            for _ in range(4):
                arg, cursor = balanced(text, cursor)
                args.append(arg)
            end = text.find(r"\end{slidepage}", cursor)
            if end < 0:
                raise RAGError("Unclosed speaker-script page.")
            raw = args[2] + "\n" + text[cursor:end]
            blocks.append(
                Block(
                    latex_plain(raw),
                    f"Slide {args[0]}: {args[1]}",
                    text.count("\n", 0, slide.start()) + 1,
                    text.count("\n", 0, end) + 1,
                )
            )
    return blocks


def json_blocks(text: str, entry: dict) -> list[Block]:
    document = json.loads(text)
    blocks = []
    if entry["format"] == "sources":
        for index, source in enumerate(document):
            keys = [
                "id",
                "title",
                "url",
                "zotero_key",
                "zotero_status",
                "summary",
                "used",
                "review_scope",
            ]
            selected = {key: source[key] for key in keys if key in source}
            blocks.append(
                Block(
                    json.dumps(selected, ensure_ascii=False, indent=2),
                    f"Source {source['id']}: {source['title']}",
                    1,
                    1,
                    locator=f"$[{index}]",
                )
            )
    else:
        for key in entry.get("json_paths", list(document)):
            value = document[key]
            values = (
                list(value.items())
                if isinstance(value, dict)
                else (list(enumerate(value)) if isinstance(value, list) else [(None, value)])
            )
            for child, item in values:
                locator = f"$.{key}" + (f"[{child!r}]" if child is not None else "")
                label = item.get("gate", child) if isinstance(item, dict) else child
                blocks.append(
                    Block(
                        json.dumps(item, ensure_ascii=False, indent=2),
                        f"{key}: {label}",
                        1,
                        1,
                        locator=locator,
                    )
                )
    return blocks


def csv_blocks(text: str, path: str) -> list[Block]:
    reader = csv.reader(io.StringIO(text))
    first = next(reader, None)
    if first is None:
        return []
    header = " | ".join(first)
    end = reader.line_num
    result = []
    for ordinal, row in enumerate(reader, 1):
        start, end = end + 1, reader.line_num
        result.append(
            Block(
                header + "\n" + " | ".join(row),
                Path(path).stem,
                start,
                end,
                locator=f"CSV data row {ordinal}",
            )
        )
    return result


def extract(text: str, entry: dict, limit: int) -> list[Block]:
    reject_secrets(text, entry["path"])
    kind = entry["format"]
    if kind == "markdown":
        blocks = markdown(text)
    elif kind == "html":
        blocks = html(text)
    elif kind.startswith("latex_"):
        blocks = latex(text, kind == "latex_notes")
    elif kind in {"json", "sources"}:
        blocks = json_blocks(text, entry)
    elif kind == "csv":
        blocks = csv_blocks(text, entry["path"])
    else:
        raise RAGError(f"Unsupported corpus format: {kind}")
    result = pack(blocks, limit)
    for block in result:
        reject_secrets(block.text, entry["path"])
    return result


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
