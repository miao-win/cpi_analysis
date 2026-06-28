#!/usr/bin/env python3
# -*- coding: utf-8 -*-

TABLE_DDL = {
    'category': '''
        CREATE TABLE IF NOT EXISTS category (
            category_id   UInt64,
            category      String,
            hierarchy     UInt8,
            weight        Float32,
            price         Nullable(Float32),
            parent        Nullable(UInt64),
            load_time     DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY (hierarchy, category_id)
        SETTINGS index_granularity = 8192
    ''',

    'product_full': '''
        CREATE TABLE IF NOT EXISTS product_full (
            product_id    UInt64,
            category_id   UInt64,
            name          String,
            weight        Float32,
            price         Nullable(Float32),
            change_count  UInt32,
            dt            Date,
            load_time     DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(dt)
        ORDER BY (dt, category_id, product_id)
        SETTINGS index_granularity = 8192
    ''',

    'product_price': '''
        CREATE TABLE IF NOT EXISTS product_price (
            product_id    UInt64,
            category_id   UInt64,
            name          String,
            price         Nullable(Float32),
            change_date   Date,
            load_time     DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(change_date)
        ORDER BY (change_date, category_id, product_id)
        SETTINGS index_granularity = 8192
    ''',

    'index_result': '''
        CREATE TABLE IF NOT EXISTS index_result (
            date          Date,
            index_level   String,
            category_id   UInt64,
            category_name String,
            index_type    String,
            index_value   Float64,
            base_date     Date,
            compute_time  DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(date)
        ORDER BY (date, index_level, category_id)
        SETTINGS index_granularity = 8192
    ''',
}

CATEGORY_COLUMNS = ['category_id', 'category', 'hierarchy', 'weight', 'price', 'parent']
PRODUCT_FULL_COLUMNS = ['product_id', 'category_id', 'name', 'weight', 'price', 'change_count', 'dt']
PRODUCT_PRICE_COLUMNS = ['product_id', 'category_id', 'name', 'price', 'change_date']
INDEX_RESULT_COLUMNS = ['date', 'index_level', 'category_id', 'category_name', 'index_type', 'index_value', 'base_date']

TABLE_COLUMNS = {
    'category': CATEGORY_COLUMNS,
    'product_full': PRODUCT_FULL_COLUMNS,
    'product_price': PRODUCT_PRICE_COLUMNS,
    'index_result': INDEX_RESULT_COLUMNS,
}


def get_create_table_sql(table_name: str) -> str:
    if table_name not in TABLE_DDL:
        raise ValueError(f"Unknown table: {table_name}. Available tables: {list(TABLE_DDL.keys())}")
    return TABLE_DDL[table_name]


def get_all_create_table_sql() -> dict:
    return TABLE_DDL.copy()