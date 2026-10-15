import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from project_rag.corpus import RAGError, default_corpus
from project_rag.evaluation import evaluate
from project_rag.index import EvidenceIndex, build_index, default_index, section_gate
from project_rag.server import create_server


@pytest.fixture
def published_clone(tmp_path):
    # Copy only the tracked publication allowlist. No private/full-workspace
    # evidence, authoring inputs, database, binary deck or existing index exists.
    source_root = Path(__file__).resolve().parents[2]
    root = tmp_path / "fresh clone with spaces"
    corpus = default_corpus("published")
    for entry in corpus["sources"]:
        source = source_root / entry["path"]
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    path = default_index(root, "published")
    build_index(root, path, corpus)
    return EvidenceIndex(root, path, corpus)


def test_profile_defaults_and_explicit_allowlist():
    assert default_corpus() == default_corpus("full")
    assert len(default_corpus()["sources"]) == 52
    assert default_index(Path("root")).name == "knowledge.sqlite"
    assert default_index(Path("root"), "published").name == "published.sqlite"
    published = default_corpus("published")
    assert published["profile"] == "published"
    assert len(published["sources"]) == 12
    paths = {entry["path"] for entry in published["sources"]}
    assert {
        "results/presentation/slide_text.md",
        "results/presentation/results_summary.json",
    } <= paths
    assert not any(
        any(word in path for word in ("speaker", "route", "answer_map", "assessment_answers"))
        for path in paths
    )
    for entry in published["sources"]:
        assert entry["format"] in {"markdown", "json"}
        assert entry["path"].startswith(("presentation/", "docs/", "scripts/", "results/"))
        assert not any(
            part in {"private", "raw", "processed", ".runtime", "build"}
            for part in Path(entry["path"]).parts
        )
    for profile in ("auto", "../custom.json", "missing"):
        with pytest.raises(RAGError, match="full or published"):
            default_corpus(profile)
        with pytest.raises(RAGError, match="full or published"):
            default_index(Path("root"), profile)


def test_published_clone_index_scope_citations_and_full_separation(published_clone):
    index = published_clone
    manifest = index.manifest()
    assert manifest["corpus_profile"] == "published" and manifest["source_count"] == 12
    assert "does not include speaker notes, private reports" in manifest["evidence_scope"]
    assert not (index.root / "docs/knowledge/current-evidence.md").exists()
    assert not default_index(index.root).exists()
    assert not (index.root / "presentation/speaker_notes.md").exists()
    summary = index.search("gate B similar solar load matching", 12)
    assert any(
        passage["source_path"] == "results/presentation/results_summary.json"
        and passage["location"].startswith("$.")
        for passage in summary["results"]
    )
    packet = index.answer_context("gate B similar solar load matching coverage", 6)
    assert packet["corpus_profile"] == "published" and not packet["must_abstain"]
    assert all(value in json.dumps(packet) for value in ["504", "1,139", "44"])
    for passage in packet["evidence"]:
        assert index.fetch(passage["id"])["text"] == passage["text"]
        assert passage["source_path"] in {r["path"] for r in index.corpus["sources"]}
    with pytest.raises(RAGError, match="configuration"):
        EvidenceIndex(index.root, index.path).manifest()


def test_published_missing_and_stale_evidence_still_fail_closed(published_clone):
    index = published_clone
    source = index.root / "results/presentation/slide_text.md"
    source.write_text(source.read_text() + "\nA dated publication edit changes this source.\n")
    with pytest.raises(RAGError, match="stale"):
        index.search("gate B")
    build_index(index.root, index.path, index.corpus)
    source.unlink()
    with pytest.raises(RAGError, match="stale"):
        index.search("gate B")
    before = index.path.read_bytes()
    with pytest.raises(RAGError, match="Missing"):
        build_index(index.root, index.path, index.corpus)
    assert index.path.read_bytes() == before


def test_published_regressions_use_their_own_cases(published_clone):
    result = evaluate(published_clone)
    assert result["corpus_profile"] == "published"
    assert result["cases"] == result["passed"] == 11, result["results"]


def test_cli_selects_published_from_environment_and_keeps_full_default(published_clone):
    index = published_clone
    env = {**os.environ, "PROJECT_RAG_CORPUS": "published"}
    env.pop("PROJECT_RAG_INDEX", None)
    args = [sys.executable, "-m", "project_rag.cli"]
    for command in ["index", "check", "evaluate"]:
        result = subprocess.run(
            [*args, command, "--root", str(index.root)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert json.loads(result.stdout)["corpus_profile"] == "published"
    result = subprocess.run(
        [*args, "search", "gate B matching", "--root", str(index.root), "--corpus", "published"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0 and json.loads(result.stdout)["results"]
    result = subprocess.run(
        [*args, "index", "--root", str(index.root), "--corpus", "full"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2 and "Missing" in result.stderr
    assert index.path.exists() and not default_index(index.root).exists()
    env["PROJECT_RAG_CORPUS"] = "not-a-profile"
    result = subprocess.run(
        [*args, "check", "--root", str(index.root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2 and "full or published" in result.stderr


async def test_published_mcp_environment_and_real_stdio(published_clone, monkeypatch):
    index = published_clone
    monkeypatch.setenv("PROJECT_RAG_ROOT", str(index.root))
    monkeypatch.setenv("PROJECT_RAG_CORPUS", "published")
    monkeypatch.delenv("PROJECT_RAG_INDEX", raising=False)
    async with Client(create_server()) as client:
        result = await client.call_tool(
            "prepare_answer", {"question": "What does a recorded binding hour measure?"}
        )
        assert result.structured_content["corpus_profile"] == "published"
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "project_rag.cli",
            "serve",
            "--root",
            str(index.root),
            "--corpus",
            "published",
        ],
    )
    async with Client(params, read_timeout_seconds=15) as client:
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == {"search_project", "fetch_evidence", "prepare_answer"}
        assert all(t.annotations.read_only_hint for t in tools)
        result = await client.call_tool("search_project", {"query": "cleaning source rows"})
        packet = result.structured_content
        assert packet["corpus_profile"] == "published" and packet["results"]
        passage = packet["results"][0]
        result = await client.call_tool("fetch_evidence", {"passage_id": passage["id"]})
        assert result.structured_content["text"] == passage["text"]
        result = await client.call_tool(
            "prepare_answer", {"question": "What is the live Western Hub LMP right now?"}
        )
        assert result.structured_content["must_abstain"]


def test_indexes_built_before_profile_metadata_still_work(fixture_index):
    with sqlite3.connect(fixture_index.path) as connection:
        manifest = json.loads(
            connection.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0]
        )
        manifest.pop("corpus_profile")
        manifest.pop("evidence_scope")
        connection.execute(
            "UPDATE metadata SET value=? WHERE key='manifest'", (json.dumps(manifest),)
        )
    result = fixture_index.search("gate B economic policy")
    assert result["corpus_profile"] == "full" and result["results"]


@pytest.mark.parametrize(
    ("heading", "gate"),
    [
        ("Report > Flowgate B > How confident are you?", "B"),
        ("Notes > 9. B: local prices", "B"),
        ("Notes > Slide 12: C wind", "C"),
        ("Report > A: demand", "A"),
        ("Report > Confidence and caveats", None),
    ],
)
def test_nearest_gate_heading_is_recognized(heading, gate):
    assert section_gate(heading) == gate
