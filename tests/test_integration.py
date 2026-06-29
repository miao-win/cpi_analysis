# -*- coding: utf-8 -*-
"""
测试3：集成测试
验证端到端流程：数据清洗 -> 写入ClickHouse -> 计算指标 -> 查询验证
需要设置环境变量 CK_HOST/CK_PORT/CK_USER/CK_PASSWORD/CK_DATABASE 才能运行。
CI环境中通过GitHub Secrets注入，无Secrets时自动跳过。
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.ingestion.cleaner import DataCleaner
from src.ingestion.ddl import TABLE_DDL, TABLE_COLUMNS


def clickhouse_available():
    """检查ClickHouse是否可连接"""
    host = os.getenv('CK_HOST')
    if not host:
        return False
    try:
        from src.storage.clickhouse_client import ClickHouseClient
        client = ClickHouseClient()
        with client:
            return client.ping()
    except Exception:
        return False


skip_no_ck = pytest.mark.skipif(
    not clickhouse_available(),
    reason='ClickHouse不可用（需设置CK_HOST等环境变量）'
)


@pytest.fixture(scope='module')
def ck_client():
    """创建共享的ClickHouse客户端"""
    from src.storage.clickhouse_client import ClickHouseClient
    client = ClickHouseClient()
    yield client
    client.close()


@pytest.fixture(scope='module')
def test_tables(ck_client):
    """在ClickHouse中创建测试表，测试结束后清理"""
    with ck_client:
        for table_name, ddl in TABLE_DDL.items():
            ck_client.execute_command(ddl)
    yield
    with ck_client:
        for table_name in TABLE_DDL.keys():
            try:
                ck_client.execute_command(f'DROP TABLE IF EXISTS {table_name}')
            except Exception:
                pass


@skip_no_ck
class TestCategoryIntegration:
    """分类数据端到端集成测试"""

    def test_insert_category_data(self, ck_client, test_tables, category_csv_bytes):
        df = DataCleaner.clean_category(category_csv_bytes)
        assert len(df) > 0

        cols = TABLE_COLUMNS['category']
        df = df[cols]

        with ck_client:
            ck_client.insert_df('category', df)
            count = ck_client.query_value('SELECT count(*) FROM category')
            assert count >= len(df)

    def test_query_category_after_insert(self, ck_client, test_tables):
        with ck_client:
            rows = ck_client.query_all('SELECT category_id, category FROM category ORDER BY category_id')
            assert len(rows) > 0
            # 验证第一条数据
            first = rows[0]
            assert first[0] > 0
            assert isinstance(first[1], str)


@skip_no_ck
class TestProductIntegration:
    """商品数据端到端集成测试"""

    def test_insert_product_data(self, ck_client, test_tables, product_csv_bytes, sample_date):
        df = DataCleaner.clean_product_full(product_csv_bytes, sample_date)
        assert len(df) > 0

        cols = TABLE_COLUMNS['product_full']
        df = df[cols]

        with ck_client:
            ck_client.insert_df('product_full', df)
            count = ck_client.query_value('SELECT count(*) FROM product_full')
            assert count >= len(df)


@skip_no_ck
class TestDailyPriceIntegration:
    """每日价格数据端到端集成测试"""

    def test_insert_daily_price_data(self, ck_client, test_tables, daily_price_csv_bytes):
        df, dt_str = DataCleaner.clean_daily_price(daily_price_csv_bytes)
        assert len(df) > 0
        assert dt_str is not None

        cols = TABLE_COLUMNS['product_price']
        df = df[cols]

        with ck_client:
            ck_client.insert_df('product_price', df)
            count = ck_client.query_value('SELECT count(*) FROM product_price')
            assert count >= len(df)

    def test_query_price_range(self, ck_client, test_tables):
        with ck_client:
            result = ck_client.query_one(
                'SELECT MIN(change_date), MAX(change_date) FROM product_price'
            )
            assert result is not None
            assert result[0] is not None
            assert result[1] is not None


@skip_no_ck
class TestIndexComputationIntegration:
    """指标计算端到端集成测试"""

    def test_compute_laspeyres_and_verify(self, ck_client, test_tables):
        from src.compute.calculator import _build_laspeyres_sql

        sql = _build_laspeyres_sql('total', '2025-05-17')
        with ck_client:
            ck_client.execute_command(sql)
            count = ck_client.query_value(
                "SELECT count(*) FROM index_result WHERE index_type = 'laspeyres'"
            )
            assert count > 0

    def test_compute_paasche_and_verify(self, ck_client, test_tables):
        from src.compute.calculator import _build_paasche_sql

        sql = _build_paasche_sql('total', '2025-05-17')
        with ck_client:
            ck_client.execute_command(sql)
            count = ck_client.query_value(
                "SELECT count(*) FROM index_result WHERE index_type = 'paasche'"
            )
            assert count > 0

    def test_compute_fisher_and_verify(self, ck_client, test_tables):
        from src.compute.calculator import _build_fisher_sql

        sql = _build_fisher_sql('total', '2025-05-17')
        with ck_client:
            ck_client.execute_command(sql)
            count = ck_client.query_value(
                "SELECT count(*) FROM index_result WHERE index_type = 'fisher'"
            )
            assert count > 0

    def test_fisher_is_geometric_mean(self, ck_client, test_tables):
        """验证Fisher指数 = sqrt(Laspeyres * Paasche)"""
        import math
        with ck_client:
            las = ck_client.query_value(
                "SELECT index_value FROM index_result "
                "WHERE index_type = 'laspeyres' AND index_level = 'total' LIMIT 1"
            )
            paa = ck_client.query_value(
                "SELECT index_value FROM index_result "
                "WHERE index_type = 'paasche' AND index_level = 'total' LIMIT 1"
            )
            fish = ck_client.query_value(
                "SELECT index_value FROM index_result "
                "WHERE index_type = 'fisher' AND index_level = 'total' LIMIT 1"
            )
            if las and paa and fish:
                expected = math.sqrt(las * paa)
                assert abs(fish - expected) < 0.0001, (
                    f"Fisher({fish}) != sqrt({las} * {paa}) = {expected}"
                )

    def test_category_level_computation(self, ck_client, test_tables):
        from src.compute.calculator import _build_laspeyres_sql

        sql = _build_laspeyres_sql('category', '2025-05-17')
        with ck_client:
            ck_client.execute_command(sql)
            count = ck_client.query_value(
                "SELECT count(*) FROM index_result WHERE index_level = 'category'"
            )
            assert count > 0
