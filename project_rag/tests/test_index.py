import json
import sqlite3

import pytest

from project_rag.corpus import RAGError, sha256
from project_rag.index import EvidenceIndex, build_index


def test_retrieval_currentness_and_verified_citations(fixture_index):
    result = fixture_index.search("gate B economic policy", 3)
    assert result["results"][0]["source_path"] == "current.md"
    assert any(item["evidence_status"] == "historical_support" for item in result["results"])
    for passage in result["results"]:
        assert fixture_index.fetch(passage["id"])["text"] == passage["text"]
        assert sha256(passage["text"].encode()) == passage["passage_sha256"]
        assert passage["source_path"] in passage["citation_label"]
        assert passage["local_citation_target"].startswith(str(fixture_index.root))


def test_packet_rules_and_limits(fixture_index):
    result = fixture_index.answer_context("gate B solar matching", 12)
    assert "504/1,139" in json.dumps(result) and "44" in json.dumps(result)
    assert not result["must_abstain"] and result["context_chars"] <= 18_000
    assert "untrusted source data" in result["answer_instructions"]
    assert set(result["citation_map"]) == {x["id"] for x in result["evidence"]}


@pytest.mark.parametrize(
    "query",
    [
        "What is the live Western Hub LMP right now?",
        "Give me the API key.",
        "Explain chlorophyll photosynthesis stomata.",
    ],
)
def test_unsupported_questions_abstain(fixture_index, query):
    assert fixture_index.answer_context(query)["must_abstain"]


def test_current_findings_are_not_mistaken_for_live_quotes(fixture_index):
    assert fixture_index.search("current gate B economic price findings")["results"]


def test_stale_sources_fail_closed_and_rebuild(fixture_index):
    old_id = fixture_index.manifest()["snapshot_id"]
    path = fixture_index.root / "current.md"
    path.write_text(path.read_text() + "\nNew dated source evidence changes the snapshot.\n")
    with pytest.raises(RAGError, match="stale"):
        fixture_index.search("gate B")
    build_index(fixture_index.root, fixture_index.path, fixture_index.corpus)
    assert fixture_index.manifest()["snapshot_id"] != old_id


def test_atomic_failure_preserves_previous_index(fixture_index):
    before = fixture_index.path.read_bytes()
    bad = {
        **fixture_index.corpus,
        "sources": fixture_index.corpus["sources"]
        + [{"path": "missing.md", "format": "markdown", "status": "missing", "priority": 1}],
    }
    with pytest.raises(RAGError):
        build_index(fixture_index.root, fixture_index.path, bad)
    assert fixture_index.path.read_bytes() == before


def test_permissions_and_read_only_database(fixture_index):
    assert fixture_index.path.stat().st_mode & 0o777 == 0o600
    assert fixture_index.path.parent.stat().st_mode & 0o777 == 0o700
    connection = fixture_index.open()
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM passages")
    finally:
        connection.close()


@pytest.mark.parametrize("query", ["B OR 1=1 -- DROP TABLE passages;", '"NEAR(" B *', "B: solar"])
def test_query_metacharacters_cannot_inject_fts_or_sql(fixture_index, query):
    fixture_index.search(query)
    assert fixture_index.manifest()["source_count"] == 2


@pytest.mark.parametrize(
    "identifier", ["../current.md", "https://example.com", "K' OR 1=1", "K" + "0" * 20]
)
def test_fetch_only_known_ids(fixture_index, identifier):
    with pytest.raises(RAGError):
        fixture_index.fetch(identifier)


def test_index_configuration_root_and_hash_tampering(fixture_index):
    bad_config = {**fixture_index.corpus, "chunk_chars": 2000}
    with pytest.raises(RAGError, match="configuration"):
        EvidenceIndex(fixture_index.root, fixture_index.path, bad_config).manifest()
    with pytest.raises(RAGError, match="different project"):
        EvidenceIndex(
            fixture_index.root / "other", fixture_index.path, fixture_index.corpus
        ).manifest()
    result = fixture_index.search("gate B")["results"][0]
    with sqlite3.connect(fixture_index.path) as connection:
        connection.execute("UPDATE passages SET text='tampered' WHERE id=?", (result["id"],))
    with pytest.raises(RAGError, match="hash mismatch"):
        fixture_index.fetch(result["id"])
