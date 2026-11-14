#!/usr/bin/env python3
"""
merge_csvs.py - Merges all Extension CSV datasets into 1 unified master CSV file:
  - sources/browser-extensions.csv (Curated open-source extensions + Top popular store extensions)
  - sources/browser-extension-repos.csv (Monitored / personal repositories)
  - Enriched with analysis results from ext-analysis/ (manifest_version, risk, permissions, background, scores)

Outputs:
  - sources/browser-extensions-merged.csv (136+ rows, unified schema)
  - sources/browser-extension-sources.csv (identical mirror)
"""

import argparse
import csv
import json
import os
import re
from pathlib import Path

from source_lab.paths import LAB_ROOT, Paths

REPO_ROOT = LAB_ROOT
SOURCES_DIR = Paths.from_env().sources
ANALYSIS_DIR = Paths.from_env().analysis

GITHUB_URL_RE = re.compile(r"github\.com[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")

def extract_slug(url_or_name: str) -> str:
    if not url_or_name:
        return ""
    m = GITHUB_URL_RE.search(url_or_name)
    if m:
        repo = m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return f"{m.group(1)}/{repo}"
    if "/" in url_or_name and not url_or_name.startswith("http"):
        return url_or_name.strip()
    return ""

def load_analysis_metadata(analysis_dir: Path = ANALYSIS_DIR) -> dict:
    meta = {}
    if not analysis_dir.exists():
        return meta

    # From summary.csv if available
    summary_path = analysis_dir / "summary.csv"
    if summary_path.exists():
        with open(summary_path, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                r = (row.get("repo") or "").strip()
                if r:
                    meta[r.lower()] = {
                        "analysis_status": row.get("status") or "PENDING",
                        "risk_level": row.get("risk_level") or "",
                        "heuristic_score": row.get("heuristic_score") or "",
                        "manifest_path": row.get("manifest_path") or "",
                        "threats_count": row.get("threats") or "0",
                    }

    # Deepen with manifest-analysis.json
    for p in analysis_dir.glob("*/manifest-analysis.json"):
        try:
            with open(p, mode="r", encoding="utf-8") as f:
                d = json.load(f)
                repo = (d.get("repo") or "").strip()
                if not repo:
                    repo = p.parent.name.replace("__", "/")
                key = repo.lower()
                existing = meta.get(key, {})
                existing["analysis_status"] = "ANALYZED"
                existing["manifest_version"] = str(d.get("manifest_version") or "")
                existing["risk_level"] = d.get("risk_level") or existing.get("risk_level", "")
                existing["heuristic_score"] = str(d.get("heuristic_score") or existing.get("heuristic_score", ""))
                existing["background_type"] = d.get("background") or ""
                existing["permissions"] = "; ".join(d.get("permissions") or [])
                existing["content_script_matches"] = "; ".join(d.get("content_scripts", {}).get("matches") or [])
                if d.get("name"):
                    existing["extension_name"] = d.get("name")
                if d.get("description"):
                    existing["description"] = d.get("description")
                meta[key] = existing
        except Exception:
            pass

    return meta

# @lat: [[source-lab#Pipeline]]
def merge_extension_csvs(sources_dir: Path = SOURCES_DIR, analysis_dir: Path = ANALYSIS_DIR, output_dir: Path | None = None):
    analysis_meta = load_analysis_metadata(analysis_dir)
    records = []
    seen_urls = set()

    # 1. Monitored / Personal Extensions
    monitored_csv = sources_dir / "browser-extension-repos.csv"
    if monitored_csv.exists():
        with open(monitored_csv, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for r in reader:
                repo_url = (r.get("repo_url") or "").strip()
                slug = extract_slug(repo_url) or extract_slug(r.get("repo_name") or "")
                meta = analysis_meta.get(slug.lower(), {})

                record = {
                    "source_dataset": "monitored_personal",
                    "category": r.get("category") or "Personal / Own Repository",
                    "extension_name": r.get("extension_name") or meta.get("extension_name") or r.get("repo_name") or "",
                    "repo_name": slug or r.get("repo_name") or "",
                    "repo_url": repo_url,
                    "description": r.get("description") or meta.get("description") or "",
                    "manifest_version": r.get("manifest_version") or meta.get("manifest_version") or "3",
                    "manifest_path": r.get("manifest_path") or meta.get("manifest_path") or "manifest.json",
                    "permissions": r.get("permissions") or meta.get("permissions") or "",
                    "background_type": r.get("background_type") or meta.get("background_type") or "",
                    "content_script_matches": r.get("content_script_matches") or meta.get("content_script_matches") or "",
                    "is_private": r.get("is_private") or "False",
                    "local_path": r.get("local_path") or "",
                    "analysis_status": meta.get("analysis_status") or "ANALYZED",
                    "risk_level": meta.get("risk_level") or "MEDIUM",
                    "heuristic_score": meta.get("heuristic_score") or "5",
                    "notes": r.get("source") or "GitHub + Local filesystem",
                }
                records.append(record)
                if repo_url:
                    seen_urls.add(repo_url.lower())
                if slug:
                    seen_urls.add(slug.lower())

    # 2. Curated Open-Source & Popular Store Extensions from browser-extensions.csv
    curated_csv = sources_dir / "browser-extensions.csv"
    if curated_csv.exists():
        with open(curated_csv, mode="r", encoding="utf-8", errors="ignore") as f:
            current_mode = "curated_opensource"
            for r in csv.DictReader(f):
                cat = (r.get("Category") or "").strip()
                ext = (r.get("Extension") or "").strip()
                link = (r.get("Repo Link") or "").strip()
                desc = (r.get("Description") or "").strip()

                if cat.lower() == "non open source":
                    current_mode = "top_popular_store"
                    continue
                if cat.lower() in ("category", "extension") or ext.lower() in ("category", "extension"):
                    continue
                if not cat and not ext and not link:
                    continue

                if current_mode == "curated_opensource":
                    if link.startswith("http"):
                        slug = extract_slug(link)
                        if link.lower() in seen_urls or (slug and slug.lower() in seen_urls):
                            continue

                        meta = analysis_meta.get(slug.lower(), {})
                        record = {
                            "source_dataset": "curated_opensource",
                            "category": cat or "General",
                            "extension_name": ext or meta.get("extension_name") or slug,
                            "repo_name": slug or ext,
                            "repo_url": link,
                            "description": desc or meta.get("description") or "",
                            "manifest_version": meta.get("manifest_version") or "",
                            "manifest_path": meta.get("manifest_path") or "",
                            "permissions": meta.get("permissions") or "",
                            "background_type": meta.get("background_type") or "",
                            "content_script_matches": meta.get("content_script_matches") or "",
                            "is_private": "False",
                            "local_path": "",
                            "analysis_status": meta.get("analysis_status") or "PENDING",
                            "risk_level": meta.get("risk_level") or "",
                            "heuristic_score": meta.get("heuristic_score") or "",
                            "notes": "Curated Open Source",
                        }
                        records.append(record)
                        seen_urls.add(link.lower())
                        if slug:
                            seen_urls.add(slug.lower())
                else:
                    # top_popular_store
                    record = {
                        "source_dataset": "top_popular_store",
                        "category": ext or cat,
                        "extension_name": cat,
                        "repo_name": "",
                        "repo_url": "",
                        "description": desc or "Commercial / Web Store Extension",
                        "manifest_version": "",
                        "manifest_path": "",
                        "permissions": "",
                        "background_type": "",
                        "content_script_matches": "",
                        "is_private": "True",
                        "local_path": "",
                        "analysis_status": "STORE_CLOSED_SOURCE",
                        "risk_level": "",
                        "heuristic_score": "",
                        "notes": link, # e.g. "207M+ installs; often auto-installed"
                    }
                    records.append(record)

    fieldnames = [
        "source_dataset",
        "category",
        "extension_name",
        "repo_name",
        "repo_url",
        "description",
        "manifest_version",
        "manifest_path",
        "permissions",
        "background_type",
        "content_script_matches",
        "is_private",
        "local_path",
        "analysis_status",
        "risk_level",
        "heuristic_score",
        "notes",
    ]

    # Write merged files
    output_dir = sources_dir if output_dir is None else output_dir
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    out_files = [
        output_dir / "browser-extensions-merged.csv",
        output_dir / "browser-extension-sources.csv",
    ]

    for out_path in out_files:
        with open(out_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in records:
                writer.writerow(rec)
        print(f"Written merged CSV: {out_path} ({len(records)} extensions)")

def main():
    parser = argparse.ArgumentParser(description="Merge extension catalogs with crawler analysis results")
    parser.add_argument("--sources", type=Path, default=SOURCES_DIR, help="Directory holding browser-extensions.csv and browser-extension-repos.csv")
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR, help="Directory holding crawler bundles and summary.csv")
    parser.add_argument("--output-dir", type=Path, default=Paths.from_env().storage / "catalogs", help="Writable output directory; resource inputs stay unchanged")
    args = parser.parse_args()
    merge_extension_csvs(args.sources, args.analysis_dir, args.output_dir)


if __name__ == "__main__":
    main()
