import pytest

from project_rag.index import EvidenceIndex, build_index


@pytest.fixture
def fixture_index(tmp_path):
    current = tmp_path / "current.md"
    current.write_text(
        "# Current evidence\n\n## Gate B economic policy\n\n"
        "The newer economic policy supersedes the old blanket rejection. At cost $3, "
        "modeled net is $562.45/$3,415.69 in 2025/2026. It loses on 88.9% of active days.\n\n"
        "## Matching support\n\n"
        "Gate B has 504/1,139 similar solar/load records; four-input support is 44. "
        "March has weak control support. This does not identify a physical branch.\n"
    )
    old = tmp_path / "old.md"
    old.write_text(
        "# Older B decision\n\nReject the gate B economic policy for weak forecast accuracy.\n"
    )
    corpus = {
        "version": 1,
        "chunk_chars": 2600,
        "sources": [
            {
                "path": "current.md",
                "format": "markdown",
                "status": "current_summary",
                "priority": 1.8,
            },
            {
                "path": "old.md",
                "format": "markdown",
                "status": "historical_support",
                "priority": 0.7,
            },
        ],
    }
    path = tmp_path / ".index/knowledge.sqlite"
    build_index(tmp_path, path, corpus)
    return EvidenceIndex(tmp_path, path, corpus)
