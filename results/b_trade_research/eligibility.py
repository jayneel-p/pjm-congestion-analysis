#!/usr/bin/env python3
"""Rebuild current PJM bid-location evidence from preserved public snapshots.

The default command is offline and needs only Python's standard library:
    .venv/bin/python results/b_trade_research/eligibility.py

--fetch is an explicit acquisition step for the four fixed primary documents.
It refuses to replace existing snapshots. The XLS reader deliberately supports
the BIFF8 subset in the hash-checked preserved workbook, not arbitrary Excel files.
This checks published endpoints, not a Gateway account, accepted path, historical
eligibility, a physical branch, or a profitable strategy. No prices are acquired.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import ssl
import struct
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
MANIFEST = SOURCES / "retrieval.json"
DOCUMENTS = {
    "inc_dec_locations": {
        "url": "https://www.pjm.com/-/media/DotCom/markets-ops/energy/day-ahead/valid-bidding-locations-for-virtual-bids.xlsx",
        "filename": "valid-bidding-locations-for-virtual-bids_2026-10-09.xlsx",
        "expected_sha256": "477d836a3d5ced64d2997f3fd7dafd4feea238a00a38feeca7186ee886446f3f",
    },
    "utc_locations": {
        "url": "https://www.pjm.com/-/media/DotCom/markets-ops/energy/day-ahead/valid-bidding-locations-for-utc-bids.xls",
        "filename": "valid-bidding-locations-for-utc-bids_2026-10-09.xls",
        "expected_sha256": "c735e9148cfe496f8f57ded99977dea385ae9e4588144bacda26e7eb33e63bbc",
    },
    "manual_11": {
        "url": "https://www.pjm.com/-/media/DotCom/documents/manuals/m11.ashx?la=en",
        "filename": "pjm_manual_11_2026-10-09.pdf",
        "expected_sha256": "2e3a4d3c6c92c828667fd0dde700f4e96768d2ffb7ecc13e60a7cf074af1fb04",
    },
    "manual_28": {
        "url": "https://www.pjm.com/-/media/DotCom/documents/manuals/m28.ashx",
        "filename": "pjm_manual_28_2026-10-09.pdf",
        "expected_sha256": "5138cf160ef61a89b3883dc075df5eb74864510237df04c554b809ca71201b93",
    },
}
TARGETS = {
    "ACCA": 34885183,
    "BASIN": 34885213,
    "BELLWOOD": 34885223,
    "DOMINION HUB": 35010337,
    "DOM_RESID_AGG": 116472939,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_snapshots() -> None:
    """One acquisition only; a later publication needs a new dated snapshot."""
    if MANIFEST.exists() or any((SOURCES / d["filename"]).exists() for d in DOCUMENTS.values()):
        raise RuntimeError("Snapshots already exist; refusing to overwrite preserved evidence.")
    SOURCES.mkdir(parents=True, exist_ok=True)
    context = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    downloads = {}
    # Stage all responses in memory so a changed workbook cannot leave half a set.
    for key, spec in DOCUMENTS.items():
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "PJM-case-source-review/1.0"})
        with urllib.request.urlopen(request, context=context, timeout=60) as response:
            data = response.read()
            metadata = {
                "requested_url": spec["url"],
                "response_url": response.geturl(),
                "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "last_modified_http": response.headers.get("Last-Modified"),
                "content_type_http": response.headers.get("Content-Type"),
                "bytes": len(data),
                "sha256": sha256(data),
                "snapshot": "sources/" + spec["filename"],
            }
        expected = spec.get("expected_sha256")
        if expected and metadata["sha256"] != expected:
            raise RuntimeError(f"{key}: current response differs from the reviewed document; inspect it before updating this audit.")
        if key.startswith("manual_") and not data.startswith(b"%PDF-"):
            raise RuntimeError(f"{key}: expected a PDF, received another response.")
        downloads[key] = (data, metadata)
    for key, (data, metadata) in downloads.items():
        (ROOT / metadata["snapshot"]).write_bytes(data)
    MANIFEST.write_text(json.dumps({k: m for k, (_, m) in downloads.items()}, indent=2) + "\n")


def read_snapshot(key: str, manifest: dict) -> bytes:
    metadata = manifest[key]
    spec = DOCUMENTS[key]
    if metadata["requested_url"] != spec["url"] or metadata["snapshot"] != "sources/" + spec["filename"]:
        raise ValueError(f"{key}: manifest URL or snapshot path mismatch")
    data = (ROOT / metadata["snapshot"]).read_bytes()
    digest = sha256(data)
    if len(data) != metadata["bytes"] or digest != metadata["sha256"]:
        raise ValueError(f"{key}: snapshot integrity check failed")
    if spec.get("expected_sha256", digest) != digest:
        raise ValueError(f"{key}: snapshot differs from the reviewed publication")
    return data


def read_xlsx(data: bytes) -> tuple[str, dict]:
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        sheets = ET.fromstring(book.read("xl/workbook.xml")).findall("s:sheets/s:sheet", ns)
        if len(sheets) != 1:
            raise ValueError("Expected the single-sheet reviewed XLSX workbook")
        sheet = sheets[0]
        relationship_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in relationships if r.get("Id") == relationship_id)
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("s:si", ns):
                shared.append("".join(t.text or "" for t in item.findall(".//s:t", ns)))
        cells = {}
        for row in ET.fromstring(book.read(path)).findall("s:sheetData/s:row", ns):
            for cell in row.findall("s:c", ns):
                ref = cell.get("r")
                node = cell.find("s:v", ns)
                value = node.text if node is not None else "".join(t.text or "" for t in cell.findall(".//s:t", ns))
                if cell.get("t") == "s":
                    value = shared[int(value)]
                column = "".join(c for c in ref if c.isalpha())
                number = int("".join(c for c in ref if c.isdigit()))
                cells[(number, column)] = value
    return sheet.get("name"), cells


def read_xls(data: bytes) -> tuple[str, dict]:
    """Read the regular-sector CFB/BIFF8 layout in the preserved UTC sheet."""
    if data[:8] != bytes.fromhex("D0CF11E0A1B11AE1"):
        raise ValueError("Expected an OLE compound XLS file")
    sector_size = 1 << struct.unpack_from("<H", data, 30)[0]
    if sector_size != 512 or struct.unpack_from("<I", data, 72)[0] != 0:
        raise ValueError("Unsupported CFB layout or extended DIFAT")

    def sector(index):
        chunk = data[(index + 1) * sector_size:(index + 2) * sector_size]
        if len(chunk) != sector_size:
            raise ValueError("Invalid CFB sector")
        return chunk

    fat_ids = [x for x in struct.unpack_from("<109I", data, 76) if x < 0xFFFFFFFA]
    fat = []
    for index in fat_ids:
        fat.extend(struct.unpack("<128I", sector(index)))

    def stream(first):
        result = bytearray()
        seen = set()
        while first < 0xFFFFFFFA:
            if first in seen or first >= len(fat):
                raise ValueError("Invalid or cyclic CFB sector chain")
            seen.add(first)
            result.extend(sector(first))
            first = fat[first]
        return bytes(result)

    directory = stream(struct.unpack_from("<I", data, 48)[0])
    workbooks = []
    for offset in range(0, len(directory), 128):
        entry = directory[offset:offset + 128]
        name_bytes = struct.unpack_from("<H", entry, 64)[0]
        name = entry[:max(0, name_bytes - 2)].decode("utf-16le")
        if name in ("Workbook", "Book"):
            length = struct.unpack_from("<Q", entry, 120)[0]
            if length < 4096:
                raise ValueError("Mini-stream XLS is outside this preserved-snapshot parser")
            workbooks.append(stream(struct.unpack_from("<I", entry, 116)[0])[:length])
    if len(workbooks) != 1:
        raise ValueError("Expected exactly one BIFF workbook stream")
    workbook = workbooks[0]
    records = []
    offset = 0
    while offset + 4 <= len(workbook):
        record_id, length = struct.unpack_from("<HH", workbook, offset)
        payload = workbook[offset + 4:offset + 4 + length]
        if len(payload) != length:
            raise ValueError("Truncated BIFF record")
        records.append((offset, record_id, payload))
        offset += 4 + length
    if offset != len(workbook):
        raise ValueError("Unexpected trailing BIFF bytes")
    sheets = []
    shared = []
    for _, record_id, payload in records:
        if record_id == 0x85:  # BOUNDSHEET
            position = struct.unpack_from("<I", payload)[0]
            nchars, flags = payload[6:8]
            name = payload[8:8 + nchars * (2 if flags & 1 else 1)].decode("utf-16le" if flags & 1 else "latin1")
            sheets.append((position, name))
        if record_id == 0xFC:  # SST; this reviewed snapshot uses no continuation
            total, unique = struct.unpack_from("<II", payload)
            cursor = 8
            for _ in range(unique):
                nchars, flags = struct.unpack_from("<HB", payload, cursor)
                cursor += 3
                runs = extension = 0
                if flags & 8:
                    runs = struct.unpack_from("<H", payload, cursor)[0]
                    cursor += 2
                if flags & 4:
                    extension = struct.unpack_from("<I", payload, cursor)[0]
                    cursor += 4
                width = nchars * (2 if flags & 1 else 1)
                text = payload[cursor:cursor + width]
                if len(text) != width:
                    raise ValueError("SST continuation is outside this snapshot parser")
                shared.append(text.decode("utf-16le" if flags & 1 else "latin1"))
                cursor += width + runs * 4 + extension
            if cursor != len(payload) or total != unique:
                raise ValueError("Unexpected shared-string layout")
    if len(sheets) != 1:
        raise ValueError("Expected the single-sheet reviewed XLS workbook")

    def rk(number):
        value = (struct.unpack("<i", struct.pack("<I", number))[0] >> 2) if number & 2 else struct.unpack("<d", struct.pack("<II", 0, number & 0xFFFFFFFC))[0]
        return value / 100 if number & 1 else value

    cells = {}
    for position, record_id, payload in records:
        if position < sheets[0][0]:
            continue
        if record_id == 0xFD:  # LABELSST
            row, column, _, index = struct.unpack("<HHHI", payload)
            cells[(row + 1, chr(65 + column))] = shared[index]
        elif record_id == 0x203:  # NUMBER
            row, column, _, number = struct.unpack("<HHHd", payload)
            cells[(row + 1, chr(65 + column))] = number
        elif record_id == 0x27E:  # RK
            row, column, _, number = struct.unpack("<HHHI", payload)
            cells[(row + 1, chr(65 + column))] = rk(number)
        elif record_id == 0xBD:  # MULRK
            row, column = struct.unpack_from("<HH", payload)
            count = (len(payload) - 6) // 6
            for index in range(count):
                cells[(row + 1, chr(65 + column + index))] = rk(struct.unpack_from("<I", payload, 6 + index * 6)[0])
        elif record_id in (0x204, 0x6):
            raise ValueError("Unsupported label/formula cell in reviewed eligibility sheet")
    return sheets[0][1], cells


def inspect_locations(sheet_name: str, cells: dict, expected_rows: int) -> dict:
    if cells.get((1, "A")) != "PNODEID" or cells.get((1, "B")) != "PNODENAME":
        raise ValueError("Unexpected published column headers")
    numbers = sorted({row for row, _ in cells if row > 1})
    rows = []
    for number in numbers:
        value = float(cells[(number, "A")])
        if not value.is_integer() or value <= 0:
            raise ValueError("Expected positive integer PNODEID")
        rows.append({"row_1_based": number, "PNODEID": int(value), "PNODENAME": cells[(number, "B")], "cell_references": {"PNODEID": f"A{number}", "PNODENAME": f"B{number}"}})
    if len(rows) != expected_rows or len({r["PNODEID"] for r in rows}) != expected_rows:
        raise ValueError("Unexpected publication row count or duplicate PNODEID")
    targets = {}
    for label, pnode in TARGETS.items():
        exact = [r for r in rows if r["PNODEID"] == pnode]
        targets[label] = {
            "queried_pnode_id": pnode,
            "published": bool(exact),
            "exact_rows": exact,
            "case_insensitive_name_substring_rows": [r for r in rows if label.casefold() in r["PNODENAME"].casefold()],
        }
    return {"sheet": sheet_name, "columns": ["PNODEID", "PNODENAME"], "header_row_1_based": 1, "published_node_count": len(rows), "targets": targets, "qualifying_dominion_rows": [r for r in rows if r["PNODEID"] in (35010337, 116472939)]}


def build_result(manifest: dict) -> dict:
    data = {key: read_snapshot(key, manifest) for key in DOCUMENTS}
    publications = {
        "inc_dec_locations": inspect_locations(*read_xlsx(data["inc_dec_locations"]), expected_rows=1524),
        "utc_locations": inspect_locations(*read_xls(data["utc_locations"]), expected_rows=47),
    }
    for key, publication in publications.items():
        publication["source"] = manifest[key]
        publication["source_parent"] = {"source_register_id": "P01", "url": "https://www.pjm.com/en/markets-and-operations/energy", "existing_verified_zotero_key": "5YIFX82R", "key_basis": "Existing project source register; linked eligibility files newly inspected, no new Zotero verification or save."}
    return {
        "scope": "Current primary PJM published bidding locations retrieved 2026-10-09; an offline reproduction of endpoint publication, not historical eligibility or an executable trade validation.",
        "acquisition": "Preserved HTTP responses; no new price measurements. UTC retrieval timestamps and HTTP Last-Modified fields are source provenance, not inferred effective dates.",
        "publications": publications,
        "manuals": {
            "manual_11": {
                "title": "PJM Manual 11: Energy & Ancillary Services Market Operations",
                "revision": 137,
                "effective_date": "2026-07-28",
                "metadata_basis": "Revision/effective date read on preserved PDF cover; scoped sections read in the hash-checked snapshot. The offline script verifies PDF integrity, not PDF text extraction.",
                "source": manifest["manual_11"],
                "source_register_id": "P06",
                "existing_verified_zotero_key": "LD2XCCEQ",
                "key_basis": "Existing project source register; current additional sections read, no new Zotero verification or save.",
                "scoped_sections": [
                    {"section": "2.3.1", "printed_pages": [21, 22], "use": "Day-ahead bidding timeline, including 11:00 Eastern prior-day close."},
                    {"section": "2.3.2", "printed_pages": [23], "use": "INC, DEC and UTC are day-ahead bid types."},
                    {"section": "2.3.2.2", "printed_pages": [24], "use": "INC/DEC eligible location categories and published list; $2,000/MWh bid limit and possible transaction-volume limit."},
                    {"section": "2.3.2.3", "printed_pages": [25], "use": "UTC published source/sink locations, total-LMP clearing and bid range of -$50 to +$50/MWh."},
                ],
            },
            "manual_28": {
                "title": "PJM Manual 28: Operating Agreement Accounting",
                "revision": 104,
                "effective_date": "2026-03-01",
                "metadata_basis": "Revision/effective date read on preserved PDF cover; scoped sections read in the hash-checked snapshot. The offline script verifies PDF integrity, not PDF text extraction.",
                "source": manifest["manual_28"],
                "source_register_id": None,
                "zotero_key": None,
                "zotero_save_verified": False,
                "source_status": "New primary source in this targeted review; no Zotero save claimed.",
                "scoped_sections": [
                    {"section": "3.3 / 3.8", "printed_pages": [23, 26, 27, 28], "use": "Day-ahead spot energy and five-minute balancing deviations."},
                    {"section": "5.3.1", "printed_pages": [60, 61], "use": "Day-ahead operating-reserve allocation, including DEC and UTC sink exposures."},
                    {"section": "5.3.2.4 / 5.3.2.5", "printed_pages": [65], "use": "Withdrawal/injection deviations, including UTC sink in withdrawal deviations."},
                    {"section": "8.2.2", "printed_pages": [90, 91], "use": "Day-ahead sink-minus-source congestion charge and balancing congestion deviations."},
                    {"section": "8.4.1", "printed_pages": [92], "use": "FTR target allocation uses day-ahead congestion differences; it is a different exposure from RT-minus-DA total basis."},
                    {"section": "9.2.2", "printed_pages": [103, 104], "use": "Day-ahead and balancing loss charges; total LMP includes more than congestion."},
                ],
            },
        },
        "limitations": [
            "ACCA, BASIN and BELLWOOD are absent by exact ID and name substring from both reviewed lists; their earlier research results cannot be treated as a directly eligible virtual trade at those exact references.",
            "DOMINION HUB 35010337 and DOM_RESID_AGG 116472939 appear in both published endpoint lists. This does not verify a specific Gateway source-to-sink path, an account's permissions, credit, clearing, transaction acceptance or actual execution.",
            "Current location publication does not establish eligibility during the January 2024-August 2026 price sample.",
            "A residual-aggregate-versus-hub trade has a different, weaker measured exposure from the three fixed local nodes and requires a separate decision-time forecast and net-cost test.",
            "Separate INC and DEC bids can clear independently; endpoint eligibility alone does not remove leg risk. Published UTC endpoints do not establish every permitted pair.",
            "Manual statements are targeted current rules, not a full tariff review, historical settlement reproduction, complete cost model or identification of anonymous Flowgate B.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Acquire the fixed public documents once; default is entirely offline.")
    args = parser.parse_args()
    if args.fetch:
        fetch_snapshots()
    manifest = json.loads(MANIFEST.read_text())
    result = build_result(manifest)
    output = ROOT / "eligibility.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {output}; checked 1,524 INC/DEC and 47 UTC published IDs from preserved snapshots.")


if __name__ == "__main__":
    main()
