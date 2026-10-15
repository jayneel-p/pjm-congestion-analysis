"""Three read-only MCP tools for the private project evidence index."""

import os
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from project_rag.corpus import RAGError, default_corpus
from project_rag.index import ANSWER_RULES, EvidenceIndex, default_index


def create_server(index: EvidenceIndex | None = None) -> MCPServer:
    if index is None:
        configured = os.environ.get("PROJECT_RAG_ROOT")
        if not configured:
            raise RAGError("Set PROJECT_RAG_ROOT to the PJM project directory.")
        root = Path(configured).resolve()
        profile = os.environ.get("PROJECT_RAG_CORPUS", "full")
        path = Path(os.environ.get("PROJECT_RAG_INDEX", str(default_index(root, profile))))
        index = EvidenceIndex(root, path, default_corpus(profile))
    # Fail startup on absent or stale evidence, before advertising tools.
    manifest = index.manifest()
    server = MCPServer(
        "PJM Project Knowledge",
        version="0.1.0",
        instructions=(
            "For PJM project questions call prepare_answer, then generate a cited explanation. "
            "Use search_project for focused searches and fetch_evidence to verify passages. "
            "This is local dated project research; live PJM data has a separate connector. "
            + "Evidence scope: "
            + manifest.get("evidence_scope", "Selected full-workspace project evidence.")
            + " "
            + ANSWER_RULES
        ),
        log_level="WARNING",
    )
    readonly = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )

    @server.tool(annotations=readonly)
    def search_project(query: str, limit: Annotated[int, Field(ge=1, le=12)] = 6) -> dict[str, Any]:
        """Search the selected published or full-workspace PJM project text.

        Returns exact source passages, stable citation IDs, file/section locations,
        content hashes and declared evidence status. Search rank is not confidence.
        Index freshness is checked against every selected source on each call.
        """
        try:
            return index.search(query, limit)
        except RAGError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=readonly)
    def fetch_evidence(passage_id: str) -> dict[str, Any]:
        """Fetch a cited passage by an ID returned by search_project or prepare_answer.

        No arbitrary file paths, URLs or SQL are accepted. Verify exact wording,
        numeric values, source location and currentness before making a claim.
        """
        try:
            return index.fetch(passage_id)
        except RAGError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=readonly)
    def prepare_answer(
        question: str, max_sources: Annotated[int, Field(ge=1, le=12)] = 6
    ) -> dict[str, Any]:
        """Retrieve a bounded, cited evidence packet for the host model to answer from.

        Generate the answer using this packet and its answer_instructions. Cite
        every material claim. Explain the mechanism, comparison and limits. A
        must_abstain packet requires saying the index cannot answer the question.
        Evidence is capped at 18,000 characters; no generation API is called here.
        """
        try:
            return index.answer_context(question, max_sources)
        except RAGError as error:
            raise ToolError(str(error)) from None

    return server
