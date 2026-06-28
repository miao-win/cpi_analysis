#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import argparse
import logging
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from src.ingestion import DataImporter
from src.compute import IndexCalculator


def cmd_create_tables():
    print("Creating tables...")
    importer = DataImporter()
    importer.create_tables()
    print("Done.")


def cmd_import_full(product_dt=None):
    importer = DataImporter()
    result = importer.run_full_import(product_dt=product_dt)
    print(f"\nImport summary: {result}")
    return result


def cmd_verify():
    print("Verifying table row counts...")
    importer = DataImporter()
    counts = importer.verify_counts()
    print("\nTable counts:")
    for table, cnt in counts.items():
        if cnt >= 0:
            print(f"  {table}: {cnt} rows")
        else:
            print(f"  {table}: table does not exist")

    calc = IndexCalculator()
    try:
        idx_count = calc.ck.query_value("SELECT count(*) FROM index_result")
        idx_dates = calc.ck.query_value("SELECT count(DISTINCT date) FROM index_result")
        print(f"  index_result: {idx_count} rows, {idx_dates} dates computed")
    except Exception:
        print(f"  index_result: table not ready or empty")
    return counts


def cmd_import_category():
    importer = DataImporter()
    n = importer.import_category()
    print(f"Imported {n} categories")


def cmd_import_product_full(dt=None):
    importer = DataImporter()
    n = importer.import_product_full(dt=dt)
    print(f"Imported {n} products")


def cmd_import_daily_price(dt=None):
    importer = DataImporter()
    n, last_dt = importer.import_product_price_by_date(dt=dt)
    print(f"Imported {n} price records, last date: {last_dt}")


def cmd_compute_indices(base_date=None, recompute=False):
    print("=" * 60)
    print("Computing price indices...")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    calc = IndexCalculator()
    if base_date:
        calc.base_date = base_date
        print(f"Using specified base date: {base_date}")

    try:
        calc.compute_all(recompute=recompute)
        print("\n" + "=" * 60)
        print(f"Index computation completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        results = calc.get_total_index_series(index_type='fisher')
        if results:
            print(f"\nTotal Fisher Index series (first 5 and last 5):")
            for r in results[:5]:
                print(f"  {r['date']}: {r['index_value']:.4f}")
            if len(results) > 10:
                print(f"  ...")
            for r in results[-5:]:
                print(f"  {r['date']}: {r['index_value']:.4f}")
    except Exception as e:
        logger.error(f"Index computation failed: {e}", exc_info=True)
        raise


def cmd_compute_latest(base_date=None):
    print("Computing indices for latest date...")
    calc = IndexCalculator()
    if base_date:
        calc.base_date = base_date
    try:
        calc.compute_latest()
        print(f"Latest date computation completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        logger.error(f"Computation failed: {e}", exc_info=True)
        raise


def cmd_run_pipeline(product_dt=None, base_date=None):
    print("=" * 60)
    print("Running full ETL pipeline (import + compute)")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    print("\n[Phase 1] Data Import...")
    importer = DataImporter()
    import_result = importer.run_full_import(product_dt=product_dt)

    print("\n[Phase 2] Index Computation...")
    calc = IndexCalculator()
    if base_date:
        calc.base_date = base_date
    calc.compute_all(recompute=False)

    print("\n" + "=" * 60)
    print(f"Full pipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Imported: {import_result}")
    counts = importer.verify_counts()
    for table, cnt in counts.items():
        status = f"{cnt} rows" if cnt >= 0 else "table not found"
        print(f"  {table}: {status}")
    idx_count = calc.ck.query_value("SELECT count(*) FROM index_result")
    idx_dates = calc.ck.query_value("SELECT count(DISTINCT date) FROM index_result")
    print(f"  index_result: {idx_count} rows, {idx_dates} dates")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='High-frequency E-commerce Price Index System')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    subparsers.add_parser('create-tables', help='Create all ClickHouse tables')

    import_parser = subparsers.add_parser('import', help='Run full import pipeline')
    import_parser.add_argument('--dt', type=str, help='Snapshot date for product_full (YYYY-MM-DD)', default=None)

    subparsers.add_parser('verify', help='Verify row counts in all tables')
    subparsers.add_parser('import-category', help='Import category data only')

    prod_parser = subparsers.add_parser('import-products', help='Import product_full data only')
    prod_parser.add_argument('--dt', type=str, help='Snapshot date (YYYY-MM-DD)', default=None)

    price_parser = subparsers.add_parser('import-prices', help='Import daily price data')
    price_parser.add_argument('--dt', type=str, help='Date to import (YYYY-MM-DD), imports all if not specified', default=None)

    compute_parser = subparsers.add_parser('compute', help='Compute price indices for all dates')
    compute_parser.add_argument('--base-date', type=str, help='Base date for index calculation (YYYY-MM-DD)', default=None)
    compute_parser.add_argument('--recompute', action='store_true', help='Truncate and recompute all indices')

    compute_latest_parser = subparsers.add_parser('compute-latest', help='Compute indices for latest date only')
    compute_latest_parser.add_argument('--base-date', type=str, help='Base date (YYYY-MM-DD)', default=None)

    pipeline_parser = subparsers.add_parser('run-pipeline', help='Run full pipeline: import all data then compute indices')
    pipeline_parser.add_argument('--dt', type=str, help='Snapshot date for product_full (YYYY-MM-DD)', default=None)
    pipeline_parser.add_argument('--base-date', type=str, help='Base date for index calculation (YYYY-MM-DD)', default=None)

    args = parser.parse_args()

    try:
        if args.command == 'create-tables':
            cmd_create_tables()
        elif args.command == 'import':
            cmd_import_full(product_dt=args.dt)
        elif args.command == 'verify':
            cmd_verify()
        elif args.command == 'import-category':
            cmd_import_category()
        elif args.command == 'import-products':
            cmd_import_product_full(dt=args.dt)
        elif args.command == 'import-prices':
            cmd_import_daily_price(dt=args.dt)
        elif args.command == 'compute':
            cmd_compute_indices(base_date=args.base_date, recompute=args.recompute)
        elif args.command == 'compute-latest':
            cmd_compute_latest(base_date=args.base_date)
        elif args.command == 'run-pipeline':
            cmd_run_pipeline(product_dt=args.dt, base_date=args.base_date)
        else:
            parser.print_help()
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
