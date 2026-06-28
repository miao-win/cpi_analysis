#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.ingestion import DataImporter


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


def main():
    parser = argparse.ArgumentParser(description='High-frequency E-commerce Price Index System - Data Import Pipeline')
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

    args = parser.parse_args()

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
    else:
        parser.print_help()


if __name__ == '__main__':
    main()