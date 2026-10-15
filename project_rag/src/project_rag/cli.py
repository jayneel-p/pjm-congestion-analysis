"""Build, check and query the local project RAG, or serve it over MCP stdio."""

import argparse
import json
import os
import sys
from pathlib import Path

from project_rag.corpus import CORPUS_PROFILES, RAGError, default_corpus
from project_rag.evaluation import evaluate
from project_rag.index import EvidenceIndex, build_index, default_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="pjm-project-rag 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("index", "check", "search", "context", "evaluate", "serve"):
        child = commands.add_parser(command)
        child.add_argument(
            "--root", type=Path, default=Path(os.environ.get("PROJECT_RAG_ROOT", "."))
        )
        child.add_argument("--index", type=Path, default=None)
        child.add_argument(
            "--corpus",
            choices=CORPUS_PROFILES,
            default=os.environ.get("PROJECT_RAG_CORPUS", "full"),
            help="full local research (default), or published repository text only",
        )
        if command in {"search", "context"}:
            child.add_argument("question")
            child.add_argument("--limit", type=int, default=6)
        if command in {"index", "check", "evaluate"}:
            child.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        corpus = default_corpus(args.corpus)
        path = (
            args.index
            or Path(os.environ.get("PROJECT_RAG_INDEX", str(default_index(root, args.corpus))))
        ).resolve()
        index = EvidenceIndex(root, path, corpus)
        if args.command == "index":
            result = build_index(root, path, corpus)
        elif args.command == "check":
            result = {"status": "fresh", **index.manifest()}
        elif args.command == "search":
            result = index.search(args.question, args.limit)
        elif args.command == "context":
            result = index.answer_context(args.question, args.limit)
        elif args.command == "evaluate":
            result = evaluate(index)
        else:
            from project_rag.server import create_server

            create_server(index).run(transport="stdio")
            return
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if getattr(args, "output", None):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered)
            args.output.chmod(0o600)
            # Keep source inventory and case-level results in the saved artifact.
            print(
                json.dumps(
                    {
                        key: value
                        for key, value in result.items()
                        if key not in {"sources", "results"}
                    },
                    indent=2,
                )
            )
        else:
            print(rendered, end="")
        if args.command == "evaluate" and result["passed"] != result["cases"]:
            raise SystemExit(1)
    except (RAGError, OSError) as error:
        print(f"Project RAG: {error}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
