"""Remove PowerPoint note parts without changing visible slides or chart data."""
import argparse
import json
from pathlib import Path
import re
import zipfile


def strip_notes(source: Path, target: Path) -> dict:
    if source.resolve() == target.resolve() or target.exists():
        raise ValueError("Use a new output path; preserve the source.")
    removed, changed = [], []
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w") as new:
        for entry in old.infolist():
            name = entry.filename
            if "/notesSlides/" in name or "/notesMasters/" in name:
                removed.append(name)
                continue
            raw = old.read(name)
            cleaned = raw
            if name == "[Content_Types].xml":
                cleaned = re.sub(rb'<Override\b[^>]*PartName="/ppt/notes(?:Slides|Masters)/[^>]*?/\s*>', b"", raw)
            elif name.endswith(".rels"):
                cleaned = re.sub(rb'<Relationship\b[^>]*Type="[^"]*/notes(?:Slide|Master)"[^>]*?/\s*>', b"", raw)
            elif name == "ppt/presentation.xml":
                cleaned = re.sub(rb'<p:notesMasterIdLst\b[^>]*>.*?</p:notesMasterIdLst>', b"", raw)
                cleaned = re.sub(rb'<p:notesSz\b[^>]*/\s*>', b"", cleaned)
            if cleaned != raw:
                changed.append(name)
            new.writestr(entry, cleaned)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("Output ZIP failed CRC check.")
        for name in archive.namelist():
            if "/notesSlides/" in name or "/notesMasters/" in name:
                raise ValueError("Note part remains.")
            if name.endswith(".rels") and re.search(rb'Type="[^"]*/notes(?:Slide|Master)"', archive.read(name)):
                raise ValueError("Note relationship remains.")
    return {"removed_parts": removed, "changed_note_declarations": changed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print(json.dumps(strip_notes(args.source, args.target), indent=2))
