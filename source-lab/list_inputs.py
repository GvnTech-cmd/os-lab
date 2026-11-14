"""Bounded, offline list parsing for guarded console previews; stdout is JSON only."""
import csv
import io
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).parent / "engine"))
from source_lab.pipeline.ext_repo_analyzer import read_xlsx_records


def parse(path: Path):
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Input exceeds limit")
    if path.suffix.lower() == ".txt":
        return [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.split("#", 1)[0].strip()]
    if path.suffix.lower() == ".xlsx":
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(e.file_size for e in entries) > 16 * 1024 * 1024:
                raise ValueError("Workbook exceeds limit")
            for entry in entries:
                if entry.filename.endswith(".xml"):
                    data = archive.read(entry)
                    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                        raise ValueError("Unsafe workbook XML")
        records = read_xlsx_records(path)
    else:
        records = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    keys = ("repo_url", "repo_link", "repolink", "repository", "repo", "full_name", "html_url", "url", "slug", "local_path", "path")
    values = []
    for record in records:
        row = {str(k).strip().lower().replace("-", "_").replace(" ", "_"): str(v).strip() for k, v in record.items() if k is not None and v is not None}
        value = next((row[k] for k in keys if row.get(k)), None)
        if value:
            values.append(value)
    return values


if __name__ == "__main__":
    try:
        values = parse(Path(sys.argv[1]))
        if not 1 <= len(values) <= 100:
            raise ValueError("Choose 1–100 targets")
        print(json.dumps(values))
    except Exception:
        print("Invalid or oversized source list", file=sys.stderr)
        raise SystemExit(1)
