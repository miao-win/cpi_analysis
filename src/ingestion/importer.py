#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
from typing import Optional, List, Dict, Tuple

import pandas as pd

from src.storage.oss_client import OSSClient
from src.storage.clickhouse_client import ClickHouseClient
from src.ingestion.cleaner import DataCleaner
from src.ingestion.ddl import TABLE_DDL, TABLE_COLUMNS


class DataImporter:
    CATEGORY_FILE_KEY = 'categories.csv'
    PRODUCT_FILE_KEY = 'products.csv'
    DAILY_PRICE_PREFIX = 'daily_price/'

    def __init__(self, oss_client: Optional[OSSClient] = None, ck_client: Optional[ClickHouseClient] = None):
        self.oss = oss_client or OSSClient()
        self.ck = ck_client or ClickHouseClient()

    def create_tables(self):
        with self.ck:
            for table_name, ddl in TABLE_DDL.items():
                print(f"Creating table: {table_name}")
                self.ck.execute_command(ddl)
            print("All tables created successfully.")

    def table_exists(self, table_name: str) -> bool:
        with self.ck:
            return self.ck.table_exists(table_name)

    def get_row_count(self, table_name: str) -> int:
        with self.ck:
            return int(self.ck.query_value(f"SELECT count(*) FROM {table_name}") or 0)

    def verify_counts(self) -> Dict[str, int]:
        counts = {}
        with self.ck:
            for table_name in TABLE_DDL.keys():
                if self.ck.table_exists(table_name):
                    counts[table_name] = int(self.ck.query_value(f"SELECT count(*) FROM {table_name}") or 0)
                else:
                    counts[table_name] = -1
        return counts

    def _insert_df(self, table_name: str, df: pd.DataFrame):
        if df.empty:
            print(f"  Skipping empty dataframe for table: {table_name}")
            return
        columns = TABLE_COLUMNS[table_name]
        df = df[columns].copy()
        with self.ck:
            self.ck.insert_df(table_name, df)
        print(f"  Inserted {len(df)} rows into {table_name}")

    def import_category(self) -> int:
        print("=" * 60)
        print("Importing category data...")
        csv_bytes = self.oss.download_bytes(self.CATEGORY_FILE_KEY)
        df = DataCleaner.clean_category(csv_bytes)
        print(f"  Cleaned {len(df)} category records")
        self._insert_df('category', df)
        return len(df)

    def import_product_full(self, dt: Optional[str] = None) -> int:
        print("=" * 60)
        print("Importing product_full data...")
        csv_bytes = self.oss.download_bytes(self.PRODUCT_FILE_KEY)
        if dt is None:
            dt = pd.Timestamp.now().strftime('%Y-%m-%d')
        df = DataCleaner.clean_product_full(csv_bytes, dt)
        print(f"  Cleaned {len(df)} product records, dt={dt}")
        self._insert_df('product_full', df)
        return len(df)

    def _list_daily_price_files(self) -> List[Dict]:
        files = self.oss.list_files(prefix=self.DAILY_PRICE_PREFIX, max_keys=1000)
        csv_files = [f for f in files if f['key'].endswith('.csv')]
        csv_files.sort(key=lambda x: x['key'])
        return csv_files

    def import_daily_price(self, oss_key: Optional[str] = None) -> Tuple[int, Optional[str]]:
        if oss_key:
            files = [{'key': oss_key}]
        else:
            files = self._list_daily_price_files()
        total_rows = 0
        last_dt = None
        for f in files:
            key = f['key']
            print(f"  Processing: {key}")
            csv_bytes = self.oss.download_bytes(key)
            df, dt = DataCleaner.clean_daily_price(csv_bytes)
            if dt is None:
                dt = DataCleaner.parse_daily_price_date(key)
            if dt:
                print(f"    Date: {dt}, Cleaned records: {len(df)}")
                self._insert_df('product_price', df)
                total_rows += len(df)
                last_dt = dt
            else:
                print(f"    Warning: Could not determine date for {key}, skipping")
        return total_rows, last_dt

    def import_product_price_by_date(self, dt: Optional[str] = None) -> Tuple[int, Optional[str]]:
        if dt:
            dt_compact = dt.replace('-', '')
            oss_key = f"{self.DAILY_PRICE_PREFIX}daily_prices_{dt_compact}.csv"
            if not self.oss.file_exists(oss_key):
                raise FileNotFoundError(f"Daily price file not found for date {dt}: {oss_key}")
            return self.import_daily_price(oss_key=oss_key)
        else:
            return self.import_daily_price()

    def run_full_import(self, product_dt: Optional[str] = None) -> Dict[str, int]:
        print("=" * 60)
        print("Starting full data import pipeline")
        print("=" * 60)

        print("\nStep 0: Creating tables (if not exist)...")
        self.create_tables()

        print("\nStep 1: Importing category (order 1/3)...")
        cat_count = self.import_category()

        print("\nStep 2: Importing product_full (order 2/3)...")
        prod_count = self.import_product_full(dt=product_dt)

        print("\nStep 3: Importing product_price (order 3/3)...")
        price_count, last_dt = self.import_daily_price()

        print("\n" + "=" * 60)
        print("Import completed. Verifying counts...")
        counts = self.verify_counts()
        for table, cnt in counts.items():
            status = f"{cnt} rows" if cnt >= 0 else "table not found"
            print(f"  {table}: {status}")
        print("=" * 60)

        return {
            'category': cat_count,
            'product_full': prod_count,
            'product_price': price_count,
        }