# -*- coding: utf-8 -*-
"""
测试1：数据格式校验与字段类型转换
验证DataCleaner对CSV数据的清洗、字段类型转换逻辑
"""
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.ingestion.cleaner import DataCleaner


class TestCategoryCleaning:
    """分类数据清洗与类型转换"""

    def test_clean_category_returns_dataframe(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_category_column_types(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        # _replace_nan_with_none 将所有列转为object，检查值的实际类型
        assert isinstance(df['category_id'].iloc[0], (int, float))
        assert isinstance(df['hierarchy'].iloc[0], (int, float))
        assert isinstance(df['weight'].iloc[0], (int, float))
        assert isinstance(df['category'].iloc[0], str)

    def test_category_required_columns_exist(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        for col in DataCleaner.CATEGORY_COLUMNS:
            assert col in df.columns, f"缺少必需列: {col}"

    def test_category_filter_invalid_ids(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        # category_id <= 0 的行应被过滤
        assert (df['category_id'] > 0).all()

    def test_parent_nullable(self, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        # 空字符串parent应转为None；整数0是合法值
        root_rows = df[df['category_id'] == 1]
        if len(root_rows) > 0:
            parent_val = root_rows.iloc[0]['parent']
            # parent字段允许为None或合法整数（如0表示无父节点）
            assert parent_val is None or isinstance(parent_val, (int, float))


class TestProductCleaning:
    """商品数据清洗与类型转换"""

    def test_clean_product_returns_dataframe(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_product_column_types(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        assert isinstance(df['product_id'].iloc[0], (int, float))
        assert isinstance(df['category_id'].iloc[0], (int, float))
        assert isinstance(df['weight'].iloc[0], (int, float))
        assert isinstance(df['change_count'].iloc[0], (int, float))

    def test_product_dt_field(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        # dt字段应为date类型或Timestamp
        for val in df['dt']:
            assert val is not None

    def test_product_filter_invalid_ids(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        assert (df['product_id'] > 0).all()

    def test_product_price_nullable(self, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        # price为null/空的行应保持None
        null_price_rows = df[df['product_id'] == 1004]
        if len(null_price_rows) > 0:
            assert null_price_rows.iloc[0]['price'] is None or pd.isna(null_price_rows.iloc[0]['price'])


class TestDailyPriceCleaning:
    """每日价格数据清洗与类型转换"""

    def test_clean_daily_price_returns_tuple(self, daily_price_csv_bytes):
        result = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_daily_price_returns_dataframe_and_date(self, daily_price_csv_bytes):
        df, dt_str = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        assert isinstance(df, pd.DataFrame)
        assert dt_str is not None
        assert isinstance(dt_str, str)

    def test_daily_price_column_types(self, daily_price_csv_bytes):
        df, _ = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        assert isinstance(df['product_id'].iloc[0], (int, float))
        assert isinstance(df['category_id'].iloc[0], (int, float))
        # change_date经过replace_nan_with_none后为date或object类型
        assert df['change_date'].iloc[0] is not None

    def test_daily_price_filter_invalid_ids(self, daily_price_csv_bytes):
        df, _ = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        assert (df['product_id'] > 0).all()

    def test_daily_price_no_null_dates(self, daily_price_csv_bytes):
        df, _ = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        # change_date为None的行应被过滤
        for val in df['change_date']:
            assert val is not None


class TestTypeConversionHelpers:
    """测试DataCleaner的类型转换工具方法"""

    def test_to_int_valid(self):
        assert DataCleaner._to_int('42') == 42
        assert DataCleaner._to_int(3.14) == 3
        assert DataCleaner._to_int(' 100 ') == 100

    def test_to_int_null(self):
        assert DataCleaner._to_int('') == 0
        assert DataCleaner._to_int('null') == 0
        assert DataCleaner._to_int(None) == 0
        assert DataCleaner._to_int('', allow_null=True) is None
        assert DataCleaner._to_int('null', allow_null=True) is None

    def test_to_float_valid(self):
        assert DataCleaner._to_float('3.14') == pytest.approx(3.14)
        assert DataCleaner._to_float(42) == pytest.approx(42.0)
        assert DataCleaner._to_float(' 2.5 ') == pytest.approx(2.5)

    def test_to_float_null(self):
        assert DataCleaner._to_float('') == 0.0
        assert DataCleaner._to_float('nan') == 0.0
        assert DataCleaner._to_float('', allow_null=True) is None

    def test_to_date_valid(self):
        d = DataCleaner._to_date('2025-05-17')
        assert d is not None
        assert d.year == 2025
        assert d.month == 5
        assert d.day == 17

    def test_to_date_formats(self):
        assert DataCleaner._to_date('2025/05/17') is not None
        assert DataCleaner._to_date('20250517') is not None
        assert DataCleaner._to_date('2025.05.17') is not None

    def test_to_date_null(self):
        assert DataCleaner._to_date('') is None
        assert DataCleaner._to_date('null') is None
        assert DataCleaner._to_date(None) is None

    def test_to_str(self):
        assert DataCleaner._to_str('hello') == 'hello'
        assert DataCleaner._to_str('  hello  ') == 'hello'
        assert DataCleaner._to_str('') == ''
        assert DataCleaner._to_str('null') == ''
        assert DataCleaner._to_str(None) == ''

    def test_parse_date_str(self):
        d = DataCleaner._parse_date_str('2025-05-17')
        assert d.year == 2025
        assert d.month == 5
        assert d.day == 17

    def test_parse_daily_price_date(self):
        assert DataCleaner.parse_daily_price_date('daily_price/daily_prices_20250517.csv') == '2025-05-17'
        assert DataCleaner.parse_daily_price_date('some_file_20250518.csv') == '2025-05-18'
        assert DataCleaner.parse_daily_price_date('no_date_here.csv') is None


class TestAutoEncoding:
    """测试CSV自动编码检测"""

    def test_read_utf8(self):
        csv_str = 'col1,col2\n1,hello\n2,world\n'
        df = DataCleaner._read_csv_auto_encoding(csv_str.encode('utf-8'))
        assert len(df) == 2
        assert list(df.columns) == ['col1', 'col2']

    def test_read_gbk(self):
        csv_str = 'col1,col2\n1,你好\n2,世界\n'
        df = DataCleaner._read_csv_auto_encoding(csv_str.encode('gbk'))
        assert len(df) == 2
        assert df.iloc[0]['col2'] == '你好'
