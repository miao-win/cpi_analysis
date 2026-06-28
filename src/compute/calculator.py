#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from src.storage.clickhouse_client import ClickHouseClient
from src.ingestion.ddl import TABLE_DDL

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_BASE_DATE = '2025-05-17'


def _build_daily_prices_subquery(dt: Optional[str] = None) -> str:
    if dt:
        return f"""
        (
            SELECT
                change_date AS dt,
                product_id,
                category_id,
                EXP(AVG(LN(price))) AS price_geom_avg
            FROM product_price
            WHERE price IS NOT NULL AND price > 0
              AND change_date = toDate('{dt}')
            GROUP BY change_date, product_id, category_id
        )
        """
    else:
        return """
        (
            SELECT
                change_date AS dt,
                product_id,
                category_id,
                EXP(AVG(LN(price))) AS price_geom_avg
            FROM product_price
            WHERE price IS NOT NULL AND price > 0
            GROUP BY change_date, product_id, category_id
        )
        """


def _build_laspeyres_sql(level: str, base_date: str, dt: Optional[str] = None) -> str:
    daily_prices = _build_daily_prices_subquery(dt)

    if level == 'total':
        category_id_col = "0 AS category_id"
        category_name_col = "'ALL' AS category_name"
        category_join = ""
        category_group = ""
    else:
        category_id_col = "dp.category_id AS category_id"
        category_name_col = "coalesce(cm.category, '') AS category_name"
        category_join = "LEFT JOIN category cm ON dp.category_id = cm.category_id"
        category_group = ", dp.category_id, cm.category"

    sql = f"""
INSERT INTO index_result (date, index_level, category_id, category_name, index_type, index_value, base_date)
SELECT
    dp.dt AS date,
    '{level}' AS index_level,
    {category_id_col},
    {category_name_col},
    'laspeyres' AS index_type,
    SUM(dp.price_geom_avg * pf_base.weight) / SUM(dp_base.price_geom_avg * pf_base.weight) AS index_value,
    toDate('{base_date}') AS base_date
FROM {daily_prices} AS dp
INNER JOIN product_full pf_base
    ON dp.product_id = pf_base.product_id
    AND pf_base.dt = toDate('{base_date}')
    AND pf_base.weight > 0
INNER JOIN {daily_prices} AS dp_base
    ON pf_base.product_id = dp_base.product_id
    AND dp_base.dt = toDate('{base_date}')
{category_join}
WHERE dp.dt >= toDate('{base_date}')
GROUP BY dp.dt{category_group}
HAVING index_value IS NOT NULL AND isFinite(index_value) AND SUM(dp_base.price_geom_avg * pf_base.weight) > 0
"""
    return sql


def _build_paasche_sql(level: str, base_date: str, dt: Optional[str] = None) -> str:
    daily_prices = _build_daily_prices_subquery(dt)

    if level == 'total':
        category_id_col = "0 AS category_id"
        category_name_col = "'ALL' AS category_name"
        category_join = ""
        category_group = ""
    else:
        category_id_col = "dp.category_id AS category_id"
        category_name_col = "coalesce(cm.category, '') AS category_name"
        category_join = "LEFT JOIN category cm ON dp.category_id = cm.category_id"
        category_group = ", dp.category_id, cm.category"

    # Paasche 指数使用当期权重，推导方式：current_weight = base_weight * (p_t / p_0)
    # 公式: SUM(p_t^2 * w_0 / p_0) / SUM(p_t * w_0)
    sql = f"""
INSERT INTO index_result (date, index_level, category_id, category_name, index_type, index_value, base_date)
SELECT
    dp.dt AS date,
    '{level}' AS index_level,
    {category_id_col},
    {category_name_col},
    'paasche' AS index_type,
    SUM(dp.price_geom_avg * dp.price_geom_avg * pf_base.weight / dp_base.price_geom_avg)
        / SUM(dp.price_geom_avg * pf_base.weight) AS index_value,
    toDate('{base_date}') AS base_date
FROM {daily_prices} AS dp
INNER JOIN product_full pf_base
    ON dp.product_id = pf_base.product_id
    AND pf_base.dt = toDate('{base_date}')
    AND pf_base.weight > 0
INNER JOIN {daily_prices} AS dp_base
    ON dp.product_id = dp_base.product_id
    AND dp_base.dt = toDate('{base_date}')
{category_join}
WHERE dp.dt >= toDate('{base_date}')
GROUP BY dp.dt{category_group}
HAVING index_value IS NOT NULL AND isFinite(index_value) AND SUM(dp.price_geom_avg * pf_base.weight) > 0
"""
    return sql


def _build_fisher_sql(level: str, base_date: str) -> str:
    sql = f"""
INSERT INTO index_result (date, index_level, category_id, category_name, index_type, index_value, base_date)
SELECT
    l.date,
    '{level}' AS index_level,
    l.category_id,
    l.category_name,
    'fisher' AS index_type,
    SQRT(l.index_value * p.index_value) AS index_value,
    toDate('{base_date}') AS base_date
FROM index_result l
INNER JOIN index_result p
    ON l.date = p.date
    AND l.index_level = p.index_level
    AND l.category_id = p.category_id
WHERE l.index_type = 'laspeyres'
  AND p.index_type = 'paasche'
  AND l.index_level = '{level}'
  AND l.index_value > 0
  AND p.index_value > 0
  AND isFinite(SQRT(l.index_value * p.index_value))
"""
    return sql


class IndexCalculator:
    def __init__(self, ck_client: Optional[ClickHouseClient] = None):
        self.ck = ck_client or ClickHouseClient()
        self.base_date = DEFAULT_BASE_DATE

    def ensure_tables(self):
        with self.ck:
            if not self.ck.table_exists('index_result'):
                logger.info("Creating index_result table...")
                self.ck.execute_command(TABLE_DDL['index_result'])
                logger.info("index_result table created.")
            else:
                logger.info("index_result table already exists.")

    def get_date_range(self) -> Dict[str, Any]:
        with self.ck:
            result = self.ck.query_one(
                "SELECT MIN(change_date) AS min_date, MAX(change_date) AS max_date "
                "FROM product_price WHERE price IS NOT NULL AND price > 0"
            )
            if result:
                return {'min_date': str(result[0]) if result[0] else None,
                        'max_date': str(result[1]) if result[1] else None}
            return {'min_date': None, 'max_date': None}

    def validate_data(self) -> bool:
        date_range = self.get_date_range()
        if not date_range['min_date'] or not date_range['max_date']:
            logger.error("No valid price data found in product_price table.")
            return False

        with self.ck:
            product_count = self.ck.query_value(
                "SELECT count() FROM product_full WHERE weight > 0 AND dt = %(dt)s",
                parameters={'dt': self.base_date}
            )
            if not product_count or product_count == 0:
                logger.warning(f"No weight data found for base date {self.base_date}. "
                               f"Attempting to use earliest product_full date.")
                earliest_dt = self.ck.query_value(
                    "SELECT MIN(dt) FROM product_full WHERE weight > 0"
                )
                if earliest_dt:
                    self.base_date = str(earliest_dt)
                    logger.info(f"Adjusted base date to earliest available product_full date: {self.base_date}")
                    product_count = self.ck.query_value(
                        "SELECT count() FROM product_full WHERE weight > 0 AND dt = %(dt)s",
                        parameters={'dt': self.base_date}
                    )
                else:
                    logger.error("No valid weight data found in product_full.")
                    return False

            base_price_count = self.ck.query_value(
                "SELECT count(DISTINCT product_id) FROM product_price "
                "WHERE change_date = %(dt)s AND price IS NOT NULL AND price > 0",
                parameters={'dt': self.base_date}
            )
            if not base_price_count or base_price_count == 0:
                logger.warning(f"No price data for base date {self.base_date}. "
                               f"Adjusting to earliest price date.")
                earliest_price_date = self.ck.query_value(
                    "SELECT MIN(change_date) FROM product_price WHERE price IS NOT NULL AND price > 0"
                )
                if earliest_price_date:
                    self.base_date = str(earliest_price_date)
                    logger.info(f"Adjusted base date to earliest price date: {self.base_date}")
                else:
                    logger.error("No valid price data found.")
                    return False

            logger.info(f"Data validation passed.")
            logger.info(f"  Base date: {self.base_date}")
            logger.info(f"  Price data range: {date_range['min_date']} to {date_range['max_date']}")
            return True

    def _delete_results_for_date(self, dt: str):
        with self.ck:
            logger.info(f"Deleting existing index results for date: {dt}")
            self.ck.execute_command(
                "ALTER TABLE index_result DELETE WHERE date = %(dt)s",
                parameters={'dt': dt}
            )

    def compute_for_date(self, dt: Optional[str] = None, recompute: bool = False):
        if dt and recompute:
            self._delete_results_for_date(dt)

        logger.info("Computing Laspeyres index (total level)...")
        laspeyres_total_sql = _build_laspeyres_sql('total', self.base_date, dt)
        with self.ck:
            self.ck.execute_command(laspeyres_total_sql)

        logger.info("Computing Laspeyres index (category level)...")
        laspeyres_cat_sql = _build_laspeyres_sql('category', self.base_date, dt)
        with self.ck:
            self.ck.execute_command(laspeyres_cat_sql)

        logger.info("Computing Paasche index (total level)...")
        paasche_total_sql = _build_paasche_sql('total', self.base_date, dt)
        with self.ck:
            self.ck.execute_command(paasche_total_sql)

        logger.info("Computing Paasche index (category level)...")
        paasche_cat_sql = _build_paasche_sql('category', self.base_date, dt)
        with self.ck:
            self.ck.execute_command(paasche_cat_sql)

        logger.info("Computing Fisher index (total level)...")
        fisher_total_sql = _build_fisher_sql('total', self.base_date)
        with self.ck:
            self.ck.execute_command(fisher_total_sql)

        logger.info("Computing Fisher index (category level)...")
        fisher_cat_sql = _build_fisher_sql('category', self.base_date)
        with self.ck:
            self.ck.execute_command(fisher_cat_sql)

        logger.info("Index computation step completed.")

    def compute_all(self, recompute: bool = False):
        logger.info("=" * 60)
        logger.info("Starting full index computation")
        logger.info(f"Default base date: {self.base_date}")
        logger.info("=" * 60)

        self.ensure_tables()

        if not self.validate_data():
            raise RuntimeError("Data validation failed. Cannot compute indices.")

        date_range = self.get_date_range()
        logger.info(f"Computing indices from {self.base_date} to {date_range['max_date']}...")

        if recompute:
            with self.ck:
                logger.info("Truncating existing index_result for full recompute...")
                self.ck.execute_command("TRUNCATE TABLE index_result")

        self.compute_for_date(dt=None)

        with self.ck:
            count = self.ck.query_value("SELECT count() FROM index_result")
            date_count = self.ck.query_value("SELECT count(DISTINCT date) FROM index_result")
            logger.info(f"Index computation finished. Total rows: {count}, Distinct dates: {date_count}")

    def compute_latest(self):
        date_range = self.get_date_range()
        if not date_range['max_date']:
            logger.error("No price data available.")
            return
        latest_dt = date_range['max_date']
        logger.info(f"Computing indices for latest date: {latest_dt}")
        self.ensure_tables()
        if not self.validate_data():
            raise RuntimeError("Data validation failed.")
        self.compute_for_date(dt=latest_dt, recompute=True)

    def get_results(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.ck:
            return self.ck.query_dicts(
                f"SELECT * FROM index_result ORDER BY date, index_level, category_id, index_type LIMIT {limit}"
            )

    def get_total_index_series(self, index_type: str = 'fisher') -> List[Dict[str, Any]]:
        with self.ck:
            return self.ck.query_dicts(
                "SELECT date, index_value FROM index_result "
                "WHERE index_level = 'total' AND index_type = %(index_type)s "
                "ORDER BY date",
                parameters={'index_type': index_type}
            )

    def get_category_index_series(self, category_id: int, index_type: str = 'fisher') -> List[Dict[str, Any]]:
        with self.ck:
            return self.ck.query_dicts(
                "SELECT date, index_value FROM index_result "
                "WHERE index_level = 'category' AND category_id = %(cat_id)s AND index_type = %(index_type)s "
                "ORDER BY date",
                parameters={'cat_id': category_id, 'index_type': index_type}
            )
