#!/usr/bin/env python3
"""
Download the Kelmarsh Wind Farm SCADA dataset from Zenodo.

Full dataset: ~400 MB zip, 6 turbines × 5 years × 10-min intervals
Sample mode:  Downloads a 1-turbine subset (~60 MB)

Usage:
    python scripts/download_kelmarsh.py                 # full dataset
    python scripts/download_kelmarsh.py --sample        # K1 only, partial
    python scripts/download_kelmarsh.py --out ./data/raw
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

ZENODO_FULL_URL = "https://zenodo.org/record/5841834/files/Kelmarsh_SCADA_2016-2021_R0.zip"
ZENODO_RECORD_URL = "https://zenodo.org/api/records/5841834"

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "raw"


def download_file(url: str, dest: Path, expected_md5: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"⬇  Downloading {url}")
    print(f"   → {dest}")

    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    md5 = hashlib.md5()

    with open(dest, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, unit_divisor=1024
    ) as bar:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            md5.update(chunk)
            bar.update(len(chunk))

    if expected_md5 and md5.hexdigest() != expected_md5:
        print(f"⚠  MD5 mismatch — got {md5.hexdigest()}, expected {expected_md5}")
    else:
        print("✅  Download complete")


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    print(f"📦  Extracting {zip_path.name} → {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        with tqdm(total=len(members), unit="files") as bar:
            for member in members:
                zf.extract(member, out_dir)
                bar.update(1)
    print("✅  Extraction complete")


def main() -> None:
    p = argparse.ArgumentParser(description="Download Kelmarsh SCADA dataset")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory")
    p.add_argument(
        "--sample",
        action="store_true",
        help="Download sample only (not implemented — use data/sample/ CSVs instead)",
    )
    p.add_argument("--extract", action="store_true", default=True, help="Extract after download")
    p.add_argument("--keep-zip", action="store_true", help="Keep ZIP after extraction")
    args = p.parse_args()

    out_dir = Path(args.out)

    if args.sample:
        print("ℹ  Sample mode: Using bundled data/sample/ CSVs (no download needed).")
        print("   Run: python scripts/ingest_sample.py")
        sys.exit(0)

    zip_dest = out_dir / "Kelmarsh_SCADA_2016-2021_R0.zip"

    if zip_dest.exists():
        print(f"ℹ  Archive already exists at {zip_dest} — skipping download")
    else:
        download_file(ZENODO_FULL_URL, zip_dest)

    if args.extract:
        extract_dir = out_dir / "kelmarsh"
        if extract_dir.exists() and list(extract_dir.glob("*.csv")):
            print(f"ℹ  Already extracted to {extract_dir}")
        else:
            extract_zip(zip_dest, extract_dir)

        if not args.keep_zip:
            zip_dest.unlink()
            print(f"🗑  Removed ZIP ({zip_dest.name})")

    print(f"\n🌬  Kelmarsh data ready at: {out_dir}")
    print("   Next: python scripts/ingest_sample.py  (or run `make bootstrap`)")


if __name__ == "__main__":
    main()
