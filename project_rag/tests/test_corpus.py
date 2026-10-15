import json

import pytest

from project_rag.corpus import (
    Block,
    RAGError,
    csv_blocks,
    extract,
    html,
    json_blocks,
    latex,
    markdown,
    pack,
    source_path,
)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.md",
        "/tmp/outside.md",
        ".env",
        ".runtime/profile.json",
        "data/raw/test.csv",
        "references/private/test.md",
        "prior_evidence/test.md",
        "credentials.json",
        "api_key.json",
        "file.sqlite",
    ],
)
def test_forbidden_sources(tmp_path, path):
    with pytest.raises(RAGError):
        source_path(tmp_path, path)


def test_symlink_denied(tmp_path):
    (tmp_path / "real.md").write_text("Evidence.")
    (tmp_path / "alias.md").symlink_to(tmp_path / "real.md")
    with pytest.raises(RAGError, match="Symlink"):
        source_path(tmp_path, "alias.md")


@pytest.mark.parametrize(
    "secret",
    [
        "sk-proj-" + "x" * 40,
        "-----BEGIN PRIVATE KEY-----",
        "PJM_API_KEY=" + "a" * 32,
    ],
)
def test_credentials_fail_closed_even_in_omitted_markup(secret):
    with pytest.raises(RAGError, match="credential"):
        extract(
            f"<script>{secret}</script><p>Enough ordinary source prose to index.</p>",
            {"path": "report.html", "format": "html"},
            2600,
        )


def test_html_exact_text_tables_anchors_without_payloads():
    blocks = html("""<html><head><title>omit head</title></head><body>
    <section id="evidence"><h2>Gate B</h2><p>Net $3,415.69 &amp; 88.9% losses.</p>
    <img src="data:image/png;base64,AAAA"><script>omit script</script>
    <svg><text>omit SVG</text></svg><div hidden><p>omit hidden</p></div>
    <table><tr><th>Year</th><th>Net</th></tr><tr><td>2026</td><td>3415.69</td></tr></table>
    <figure id="chart-b"><figcaption>504/1,139 supported hours, not cause.</figcaption></figure>
    </section></body></html>""")
    joined = "\n".join(block.text for block in blocks)
    assert "$3,415.69 & 88.9%" in joined
    assert "Year | Net\n2026 | 3415.69" in joined
    assert "504/1,139" in joined
    assert not any(token in joined for token in ["AAAA", "omit", "data:image"])
    assert blocks[-1].anchor == "chart-b"
    assert all(block.section == "Gate B" for block in blocks)


def test_markdown_retains_boundaries_but_excludes_utility_status():
    text = (
        "# Evidence\n\n## PJM API MCP\n\nDo not index utility state.\n\n"
        "## Prices\n\n$3.00 exact value and sufficient text.\n"
    )
    blocks = markdown(text)
    assert not any("utility state" in block.text for block in blocks)
    assert blocks[-1].start == 9 and blocks[-1].end == 9
    assert blocks[-1].section == "Evidence > Prices"


def test_latex_notes_exclude_drawing_code_preserve_numbers():
    text = r"""\begin{frame}[t]{Gate B decision}
    \draw (0,0) -- (1,1); \node{not prose};
    \note{Cost \$3, net \$3,415.69; losses 88.9\%. {A nested clause} remains.}
    \end{frame}"""
    blocks = latex(text, True)
    assert len(blocks) == 1 and blocks[0].section == "Gate B decision"
    assert "$3,415.69" in blocks[0].text and "88.9%" in blocks[0].text
    assert "nested clause" in blocks[0].text and "draw" not in blocks[0].text


def test_json_selects_only_declared_fields():
    blocks = json_blocks(
        json.dumps({"gates": {"B": {"records": 504}}, "excluded": "omit"}),
        {"format": "json", "json_paths": ["gates"]},
    )
    assert len(blocks) == 1 and blocks[0].locator == "$.gates['B']"
    assert "504" in blocks[0].text and "omit" not in blocks[0].text


def test_multiline_csv_locations_and_header():
    blocks = csv_blocks('gate,note,value\nB,"two\nlines",504\nC,ordinary,44\n', "data.csv")
    assert (blocks[0].start, blocks[0].end) == (2, 3)
    assert (blocks[1].start, blocks[1].end) == (4, 4)
    assert "gate | note | value" in blocks[0].text


def test_chunks_are_bounded_without_splitting_numbers():
    blocks = pack([Block("$3,415.69 and 88.9% " * 80, "Evidence", 1, 4)], 100)
    assert len(blocks) > 1 and max(len(block.text) for block in blocks) <= 100
    assert all("$3,415.69" in block.text for block in blocks)
    with pytest.raises(RAGError, match="oversized"):
        pack([Block("x" * 101, "Evidence", 1, 4)], 100)
