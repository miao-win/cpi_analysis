# -*- coding: utf-8 -*-
"""
测试2：单元测试
使用小规模CSV fixtures验证数据清洗后的结构正确性，验证SQL构建正确性
（无需实际连接OSS或ClickHouse）
"""
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.ingestion.cleaner import DataCleaner
from src.ingestion.ddl import TABLE_DDL, TABLE_COLUMNS, get_create_table_sql, get_all_create_table_sql
from src.compute.calculator import (
    _build_laspeyres_sql,
    _build_paasche_sql,
    _build_fisher_sql,
    _build_daily_prices_subquery,
)


class TestDDLSchema:
    """DDL表结构定义测试"""

    def test_all_tables_have_ddl(self):
        expected = {'category', 'product_full', 'product_price', 'index_result'}
        assert set(TABLE_DDL.keys()) == expected

    def test_all_tables_have_columns(self):
        expected = {'category', 'product_full', 'product_price', 'index_result'}
        assert set(TABLE_COLUMNS.keys()) == expected

    def test_category_ddl_contains_engine(self):
        ddl = TABLE_DDL['category']
        assert 'MergeTree' in ddl
        assert 'category_id' in ddl

    def test_product_full_ddl_contains_partition(self):
        ddl = TABLE_DDL['product_full']
        assert 'PARTITION BY' in ddl
        assert 'product_id' in ddl

    def test_index_result_ddl(self):
        ddl = TABLE_DDL['index_result']
        assert 'index_type' in ddl
        assert 'index_value' in ddl

    def test_get_create_table_sql(self):
        sql = get_create_table_sql('category')
        assert 'CREATE TABLE' in sql

    def test_get_create_table_sql_unknown_raises(self):
        with pytest.raises(ValueError, match='Unknown table'):
            get_create_table_sql('nonexistent_table')

    def test_get_all_create_table_sql(self):
        all_ddl = get_all_create_table_sql()
        assert len(all_ddl) == 4


class TestTableColumnsMapping:
    """验证表列定义与DDL的一致性"""

    def test_category_columns(self):
        cols = TABLE_COLUMNS['category']
        assert cols == ['category_id', 'category', 'hierarchy', 'weight', 'price', 'parent']

    def test_product_full_columns(self):
        cols = TABLE_COLUMNS['product_full']
        assert cols == ['product_id', 'category_id', 'name', 'weight', 'price', 'change_count', 'dt']

    def test_product_price_columns(self):
        cols = TABLE_COLUMNS['product_price']
        assert cols == ['product_id', 'category_id', 'name', 'price', 'change_date']

    def test_index_result_columns(self):
        cols = TABLE_COLUMNS['index_result']
        assert cols == ['date', 'index_level', 'category_id', 'category_name', 'index_type', 'index_value', 'base_date']


class TestCleanerOutputStructure:
    """验证清洗后的DataFrame结构匹配目标表列"""

    def test_category_output_columns_match_ddl(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        expected_cols = TABLE_COLUMNS['category']
        assert list(df.columns) == expected_cols

    def test_product_output_columns_match_ddl(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        expected_cols = TABLE_COLUMNS['product_full']
        assert list(df.columns) == expected_cols

    def test_daily_price_output_columns_match_ddl(self, daily_price_csv_bytes):
        df, _ = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        expected_cols = TABLE_COLUMNS['product_price']
        assert list(df.columns) == expected_cols

    def test_category_row_count(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        assert len(df) == 6  # 全部6行都有效

    def test_product_row_count(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        assert len(df) == 5

    def test_daily_price_row_count(self, daily_price_csv_bytes):
        df, _ = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        assert len(df) == 10


class TestCleanerDataIntegrity:
    """验证清洗后数据的业务完整性"""

    def test_category_weights_positive(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        assert (df['weight'] > 0).all()

    def test_product_weights_positive(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        assert (df['weight'] > 0).all()

    def test_daily_price_positive(self, daily_price_csv_bytes):
        df, _ = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        valid_prices = df[df['price'].notna()]
        assert (valid_prices['price'] > 0).all()

    def test_category_names_not_empty(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        assert all(len(str(n).strip()) > 0 for n in df['category'])

    def test_product_names_not_empty(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        assert all(len(str(n).strip()) > 0 for n in df['name'])

    def test_daily_price_two_dates(self, daily_price_csv_bytes):
        df, _ = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        unique_dates = df['change_date'].dropna().unique()
        assert len(unique_dates) == 2


class TestSQLBuilderLaspeyres:
    """Laspeyres指数SQL构建测试"""

    def test_total_level_sql_structure(self):
        sql = _build_laspeyres_sql('total', '2025-05-17')
        assert 'INSERT INTO index_result' in sql
        assert "'laspeyres'" in sql
        assert "'total'" in sql
        assert 'SUM(' in sql
        assert 'GROUP BY' in sql

    def test_category_level_sql_structure(self):
        sql = _build_laspeyres_sql('category', '2025-05-17')
        assert "'category'" in sql
        assert 'category_id' in sql
        assert 'category_name' in sql

    def test_with_specific_date_filter(self):
        sql = _build_laspeyres_sql('total', '2025-05-17', '2025-05-18')
        assert "change_date = toDate('2025-05-18')" in sql

    def test_base_date_in_sql(self):
        sql = _build_laspeyres_sql('total', '2025-05-17')
        assert "toDate('2025-05-17')" in sql


class TestSQLBuilderPaasche:
    """Paasche指数SQL构建测试"""

    def test_total_level_sql_structure(self):
        sql = _build_paasche_sql('total', '2025-05-17')
        assert 'INSERT INTO index_result' in sql
        assert "'paasche'" in sql
        assert "'total'" in sql

    def test_category_level_sql_structure(self):
        sql = _build_paasche_sql('category', '2025-05-17')
        assert "'category'" in sql


class TestSQLBuilderFisher:
    """Fisher指数SQL构建测试"""

    def test_fisher_uses_laspeyres_and_paasche(self):
        sql = _build_fisher_sql('total', '2025-05-17')
        assert "'laspeyres'" in sql
        assert "'paasche'" in sql
        assert 'SQRT(' in sql
        assert "'fisher'" in sql

    def test_fisher_category_level(self):
        sql = _build_fisher_sql('category', '2025-05-17')
        assert "'category'" in sql


class TestDailyPricesSubquery:
    """每日价格子查询构建测试"""

    def test_without_date_filter(self):
        sql = _build_daily_prices_subquery()
        assert 'product_price' in sql
        assert 'price_geom_avg' in sql
        assert 'EXP(AVG(LN' in sql

    def test_with_date_filter(self):
        sql = _build_daily_prices_subquery('2025-05-17')
        assert "change_date = toDate('2025-05-17')" in sql
