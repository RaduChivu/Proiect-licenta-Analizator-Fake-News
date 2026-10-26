#!/usr/bin/env python3
"""
run_calibration.py — Resumable calibration benchmark for SNACTS-RO.

Processes calibration_90.json one statement at a time via the /chat API.
Tracks progress in progress.json and writes results to results.jsonl (append-only).
Can be stopped at any time and resumed without re-checking completed statements.

Usage:
    python benchmark/run_calibration.py
    python benchmark/run_calibration.py --url http://localhost:8000 --limit 10
    python benchmark/run_calibration.py --from-id T3-07
    python benchmark/run_calibration.py --reset
"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
DATASET_FILE = SCRIPT_DIR / "calibration_90.json"
OUTPUT_DIR = SCRIPT_DIR / "out"
PROGRESS_FILE = OUTPUT_DIR / "calibration_progress.json"
RESULTS_FILE = OUTPUT_DIR / "calibration_results.jsonl"
DEFAULT_API_URL = "http://localhost:8000"

VERDICT_MAP = {
    "CONFIRMAT": "TRUE",
    "INFIRMAT": "FALSE",
    "INSUFICIENT VERIFICAT": "UNCERTAIN",
}


def load_dataset(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_progress(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "dataset_name": "calibration_90",
        "started_at": None,
        "updated_at": None,
        "completed_ids": [],
        "last_completed_id": None,
        "total_completed": 0,
    }


def save_progress(path: Path, progress: dict):
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_result(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def reconcile_progress(progress: dict, results_path: Path) -> dict:
    """Ensure progress includes all IDs found in results.jsonl (crash recovery)."""
    if not results_path.exists():
        return progress
    completed = set(progress["completed_ids"])
    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    result = json.loads(line)
                    completed.add(result["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    progress["completed_ids"] = sorted(completed)
    progress["total_completed"] = len(completed)
    if progress["completed_ids"]:
        progress["last_completed_id"] = progress["completed_ids"][-1]
    return progress


def call_api(url: str, statement: str, timeout: int = 120) -> dict:
    response = requests.post(
        f"{url}/chat",
        json={"messages": [{"role": "user", "content": statement}], "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def normalize_verdict(verdict_raw: str) -> str:
    return VERDICT_MAP.get(verdict_raw, "UNCERTAIN")


def process_statement(api_url: str, item: dict, timeout: int) -> dict | None:
    try:
        response = call_api(api_url, item["statement"], timeout)
    except requests.ConnectionError:
        print(f"  [EROARE] Nu s-a putut conecta la {api_url}", file=sys.stderr)
        return None
    except requests.Timeout:
        print(f"  [EROARE] Timeout pentru {item['id']}", file=sys.stderr)
        return None
    except requests.HTTPError as e:
        print(f"  [EROARE] HTTP {e.response.status_code} pentru {item['id']}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [EROARE] {e} pentru {item['id']}", file=sys.stderr)
        return None

    verdict_api = response.get("verdict", "")
    confidence = response.get("confidence")

    return {
        "id": item["id"],
        "statement": item["statement"],
        "verdict_api": verdict_api,
        "normalized_result": normalize_verdict(verdict_api),
        "justification": response.get("justification", ""),
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run(args: argparse.Namespace):
    dataset = load_dataset(DATASET_FILE)

    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
        if RESULTS_FILE.exists():
            RESULTS_FILE.unlink()
        print("Progres resetat.")

    progress = load_progress(PROGRESS_FILE)
    progress = reconcile_progress(progress, RESULTS_FILE)

    if progress["started_at"] is None:
        progress["started_at"] = datetime.now(timezone.utc).isoformat()

    completed_set = set(progress["completed_ids"])

    if args.from_id:
        found = False
        filtered = []
        for item in dataset:
            if item["id"] == args.from_id:
                found = True
            if found:
                filtered.append(item)
        if not found:
            print(f"ID-ul {args.from_id} nu a fost găsit în dataset.", file=sys.stderr)
            sys.exit(1)
        dataset = filtered

    pending = [item for item in dataset if item["id"] not in completed_set]

    if args.limit is not None:
        pending = pending[: args.limit]

    if not pending:
        print("Toate afirmațiile au fost deja verificate.")
        return

    previously_completed = len(completed_set)
    completed_this_run = 0
    skipped = 0
    start_time = time.time()

    print(f"Dataset: {DATASET_FILE.name}")
    print(f"API:     {args.url}")
    print(f"Total:   {len(load_dataset(DATASET_FILE))}")
    print(f"Deja completate: {previously_completed}")
    print(f"De verificat acum: {len(pending)}")
    print()

    for item in tqdm(pending, desc="Verificare", unit="stmt"):
        result = process_statement(args.url, item, args.timeout)

        if result is None:
            skipped += 1
            continue

        append_result(RESULTS_FILE, result)

        progress["completed_ids"].append(item["id"])
        progress["last_completed_id"] = item["id"]
        progress["total_completed"] = len(progress["completed_ids"])
        save_progress(PROGRESS_FILE, progress)

        completed_this_run += 1

    elapsed = time.time() - start_time
    total_dataset = len(load_dataset(DATASET_FILE))

    print()
    print("=" * 50)
    print("  SUMAR RULARE CALIBRARE")
    print("=" * 50)
    print(f"  Total în dataset:       {total_dataset}")
    print(f"  Completate acum:        {completed_this_run}")
    print(f"  Completate anterior:    {previously_completed}")
    print(f"  Omise (erori):          {skipped}")
    print(f"  Total completate:       {progress['total_completed']}")
    print(f"  Rămase:                 {total_dataset - progress['total_completed']}")
    print(f"  Timp scurs:             {elapsed:.1f}s")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark de calibrare resumabil pentru SNACTS-RO"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"URL-ul API-ului (implicit: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Resetează progresul și începe de la zero",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Procesează doar următoarele N afirmații neverificate",
    )
    parser.add_argument(
        "--from-id",
        default=None,
        metavar="ID",
        help="Reia de la un ID specific (ex: T3-07)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=500,
        metavar="SECONDS",
        help="Timeout pentru fiecare cerere API (implicit: 120s)",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
