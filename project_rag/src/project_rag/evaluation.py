"""Curated retrieval regressions, not a held-out answer-accuracy benchmark."""

import json
import time
from importlib.resources import files

from project_rag.index import EvidenceIndex


def evaluate(index: EvidenceIndex, cases: list[dict] | None = None) -> dict:
    resource = (
        "evaluation_published.json"
        if index.corpus.get("profile", "full") == "published"
        else "evaluation.json"
    )
    cases = cases or json.loads(files("project_rag").joinpath(resource).read_text())
    rows = []
    for case in cases:
        start = time.perf_counter()
        result = index.answer_context(case["question"], 5)
        evidence = result["evidence"]
        joined = "\n".join(item["text"] for item in evidence).casefold()
        paths = [item["source_path"] for item in evidence]
        missing = [term for term in case.get("contains", []) if term.casefold() not in joined]
        expected = case.get("sources", [])
        source_hit = not expected or any(path in expected for path in paths)
        abstention = result["must_abstain"] == case.get("abstain", False)
        passed = source_hit and not missing and abstention
        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "passed": passed,
                "source_hit_at_5": source_hit,
                "missing_terms": missing,
                "abstention_matches": abstention,
                "passage_ids": [x["id"] for x in evidence],
                "source_paths": paths,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        )
    latencies = sorted(row["latency_ms"] for row in rows)
    return {
        "scope": (
            "Curated project retrieval regressions; not held-out or generated-answer accuracy."
        ),
        "snapshot_id": index.manifest()["snapshot_id"],
        "corpus_profile": index.corpus.get("profile", "full"),
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "median_latency_ms": latencies[len(latencies) // 2],
        "max_latency_ms": max(latencies),
        "results": rows,
    }
