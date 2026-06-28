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
from src.visualization import DataVisualizer


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


def cmd_plot_total(start_date=None, end_date=None, save=None, no_show=False):
    print("Plotting total index trend...")
    viz = DataVisualizer()
    date_range = viz.get_date_range()
    print(f"Data available from {date_range['min_date']} to {date_range['max_date']}")
    save_path = save or 'total_index_trend.png'
    viz.plot_total_index(
        start_date=start_date,
        end_date=end_date,
        save_path=save_path,
        show=not no_show
    )
    print(f"Plot saved to: {viz.output_dir}/{save_path}")


def cmd_plot_category(category_id, start_date=None, end_date=None, save=None, no_show=False):
    print(f"Plotting category index trend for category_id={category_id}...")
    viz = DataVisualizer()
    save_path = save or f'category_{category_id}_index_trend.png'
    viz.plot_category_index(
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        save_path=save_path,
        show=not no_show
    )
    print(f"Plot saved to: {viz.output_dir}/{save_path}")


def cmd_list_categories():
    print("Available categories:")
    viz = DataVisualizer()
    categories = viz.get_available_categories()
    if not categories:
        print("  No categories found.")
        return
    print(f"  {'ID':<10} {'Name':<30}")
    print(f"  {'-'*10} {'-'*30}")
    for cat in categories:
        print(f"  {cat['category_id']:<10} {cat['category_name']:<30}")


def cmd_export(format='csv', start_date=None, end_date=None, output=None):
    print(f"Exporting index data to {format}...")
    viz = DataVisualizer()
    date_range = viz.get_date_range()
    print(f"Data available from {date_range['min_date']} to {date_range['max_date']}")
    file_path = viz.export_all_data(
        start_date=start_date,
        end_date=end_date,
        format=format,
        filename=output
    )
    print(f"Data exported successfully to: {file_path}")


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

    plot_total_parser = subparsers.add_parser('plot-total', help='Plot total index trend chart')
    plot_total_parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)', default=None)
    plot_total_parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)', default=None)
    plot_total_parser.add_argument('--save', type=str, help='Output filename (default: total_index_trend.png)', default=None)
    plot_total_parser.add_argument('--no-show', action='store_true', help='Do not display plot window')

    plot_cat_parser = subparsers.add_parser('plot-category', help='Plot category index trend chart')
    plot_cat_parser.add_argument('--category-id', type=int, required=True, help='Category ID')
    plot_cat_parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)', default=None)
    plot_cat_parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)', default=None)
    plot_cat_parser.add_argument('--save', type=str, help='Output filename', default=None)
    plot_cat_parser.add_argument('--no-show', action='store_true', help='Do not display plot window')

    subparsers.add_parser('list-categories', help='List all available categories with index data')

    export_parser = subparsers.add_parser('export', help='Export index result data')
    export_parser.add_argument('--format', type=str, choices=['csv', 'excel'], default='csv', help='Export format (default: csv)')
    export_parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)', default=None)
    export_parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)', default=None)
    export_parser.add_argument('--output', type=str, help='Output filename', default=None)

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
        elif args.command == 'plot-total':
            cmd_plot_total(
                start_date=args.start_date,
                end_date=args.end_date,
                save=args.save,
                no_show=args.no_show
            )
        elif args.command == 'plot-category':
            cmd_plot_category(
                category_id=args.category_id,
                start_date=args.start_date,
                end_date=args.end_date,
                save=args.save,
                no_show=args.no_show
            )
        elif args.command == 'list-categories':
            cmd_list_categories()
        elif args.command == 'export':
            cmd_export(
                format=args.format,
                start_date=args.start_date,
                end_date=args.end_date,
                output=args.output
            )
        else:
            parser.print_help()
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
