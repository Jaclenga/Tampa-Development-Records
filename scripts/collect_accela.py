#!/usr/bin/env python3
"""Collect bounded, anonymous public records from Tampa Accela ACA."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tampa_accela import AccelaClient, CollectionError, CollectorConfig, MODULES, SearchQuery
from tampa_accela.client import RawStore
from tampa_accela.matching import match_gis_file
from tampa_accela.output import write_collection_outputs


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from exc


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Respectfully collect public Tampa ACA records using a bounded search.",
        epilog="The collector stops on access restrictions/CAPTCHA and never attempts a bypass.",
    )
    value.add_argument("--module", required=True, choices=MODULES)
    value.add_argument("--from-date", type=parse_date)
    value.add_argument("--to-date", type=parse_date)
    value.add_argument("--updated-since", type=parse_date)
    value.add_argument("--record-number")
    value.add_argument("--include-addresses", action="store_true")
    value.add_argument("--include-parcels", action="store_true")
    value.add_argument("--include-inspections", action="store_true")
    value.add_argument("--max-records", type=int)
    value.add_argument("--max-pages", type=int, default=500)
    value.add_argument("--requests-per-second", type=float, default=1.0)
    value.add_argument("--raw-root", type=Path, default=ROOT / "data" / "raw" / "accela")
    value.add_argument("--output-dir", type=Path, default=ROOT / "data" / "processed")
    value.add_argument("--checkpoint", type=Path)
    value.add_argument("--resume", action="store_true", help="Reuse a matching checkpoint; pages replay safely")
    value.add_argument(
        "--use-export", action="store_true",
        help="Use ACA's public Download results CSV for a bounded list-only collection",
    )
    value.add_argument("--run-id")
    value.add_argument("--match-gis", type=Path, help="Write a conservative crosswalk to this GIS source_records CSV")
    value.add_argument("--dry-run", action="store_true")
    value.add_argument("--verbose", action="store_true")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    if args.max_records is not None and args.max_records < 1:
        parser().error("--max-records must be positive")
    if args.max_pages < 1:
        parser().error("--max-pages must be positive")
    query = SearchQuery(
        module=args.module,
        from_date=args.from_date,
        to_date=args.to_date,
        record_number=args.record_number,
        updated_since=args.updated_since,
    )
    try:
        query.validate()
        config = CollectorConfig(requests_per_second=args.requests_per_second, max_pages=args.max_pages)
    except ValueError as exc:
        parser().error(str(exc))
    now = dt.datetime.now(dt.timezone.utc)
    run_id = args.run_id or now.strftime("%Y%m%dT%H%M%SZ")
    raw_root = args.raw_root / now.date().isoformat()
    checkpoint = args.checkpoint or (args.output_dir / "accela_checkpoints" / f"{args.module.lower()}-{run_id}.json")
    plan = {
        "module": args.module,
        "from_date": args.from_date.isoformat() if args.from_date else None,
        "to_date": args.to_date.isoformat() if args.to_date else None,
        "record_number": args.record_number,
        "raw_root": str(raw_root),
        "output_dir": str(args.output_dir),
        "checkpoint": str(checkpoint),
        "resume": args.resume,
        "requests_per_second": args.requests_per_second,
        "include_addresses": args.include_addresses,
        "include_parcels": args.include_parcels,
        "include_inspections": args.include_inspections,
        "max_records": args.max_records,
        "use_export": args.use_export,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    if checkpoint.exists() and not args.resume:
        parser().error(f"checkpoint already exists; pass --resume or choose a new --run-id: {checkpoint}")
    raw_store = RawStore(raw_root, args.module, run_id)
    try:
        with AccelaClient(config) as client:
            result = client.collect(
                query,
                raw_store=raw_store,
                checkpoint_path=checkpoint,
                include_addresses=args.include_addresses,
                include_parcels=args.include_parcels,
                include_inspections=args.include_inspections,
                max_records=args.max_records,
                use_export=args.use_export,
            )
    except (CollectionError, OSError, ValueError) as exc:
        logging.error("collection stopped safely: %s", exc)
        return 2
    paths = write_collection_outputs(
        args.output_dir,
        result,
        module=args.module,
        run_id=run_id,
        query=plan,
    )
    if args.match_gis:
        paths["crosswalk"] = str(args.output_dir / "accela_gis_crosswalk.csv")
        match_gis_file(result.records, args.match_gis, Path(paths["crosswalk"]))
    failed = any(gap.get("type") == "collection_failed" for gap in result.gaps)
    print(json.dumps({
        "records": len(result.records), "inspections": len(result.inspections),
        "incomplete": bool(result.gaps), "paths": paths,
    }, indent=2))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
