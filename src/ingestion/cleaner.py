#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
from datetime import datetime, date
from typing import Optional, Tuple

import pandas as pd


class DataCleaner:
    CATEGORY_COLUMNS = ['category_id', 'category', 'hierarchy', 'weight', 'price', 'parent']
    PRODUCT_COLUMNS = ['product_id', 'category_id', 'name', 'weight', 'price', 'change_count']
    DAILY_PRICE_COLUMNS = ['product_id', 'category_id', 'name', 'price', 'change_date']

    NULL_VALUES = {'', ' ', 'null', 'NULL', 'None', 'none', 'nan', 'NaN', 'NAN', 'NA', '#N/A'}

    @staticmethod
    def _to_int(value, allow_null: bool = False) -> Optional[int]:
        if pd.isna(value) or str(value).strip() in DataCleaner.NULL_VALUES:
            return None if allow_null else 0
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None if allow_null else 0

    @staticmethod
    def _to_float(value, allow_null: bool = False) -> Optional[float]:
        if pd.isna(value) or str(value).strip() in DataCleaner.NULL_VALUES:
            return None if allow_null else 0.0
        try:
            return float(str(value).strip())
        except (ValueError, TypeError):
            return None if allow_null else 0.0

    @staticmethod
    def _to_date(value) -> Optional[date]:
        if pd.isna(value) or str(value).strip() in DataCleaner.NULL_VALUES:
            return None
        value_str = str(value).strip()
        formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y%m%d',
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
            '%Y.%m.%d',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value_str, fmt).date()
            except ValueError:
                continue
        try:
            return pd.to_datetime(value_str).date()
        except Exception:
            return None

    @staticmethod
    def _parse_date_str(dt_str: str) -> date:
        return datetime.strptime(dt_str, '%Y-%m-%d').date()

    @staticmethod
    def _to_str(value) -> str:
        if pd.isna(value) or str(value).strip() in DataCleaner.NULL_VALUES:
            return ''
        return str(value).strip()

    @staticmethod
    def _read_csv_auto_encoding(csv_bytes: bytes) -> pd.DataFrame:
        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'utf-8-sig']
        last_error = None
        for enc in encodings:
            try:
                return pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding=enc)
            except UnicodeDecodeError as e:
                last_error = e
                continue
        raise last_error or UnicodeDecodeError('utf-8', b'', 0, 1, 'Could not decode CSV with any supported encoding')

    @classmethod
    def clean_category(cls, csv_bytes: bytes) -> pd.DataFrame:
        df = cls._read_csv_auto_encoding(csv_bytes)
        for col in cls.CATEGORY_COLUMNS:
            if col not in df.columns:
                df[col] = ''
        df = df[cls.CATEGORY_COLUMNS].copy()
        df['category'] = df['category'].apply(cls._to_str)
        df['category_id'] = df['category_id'].apply(lambda x: cls._to_int(x, allow_null=False))
        df['hierarchy'] = df['hierarchy'].apply(lambda x: cls._to_int(x, allow_null=False))
        df['weight'] = df['weight'].apply(lambda x: cls._to_float(x, allow_null=False))
        df['price'] = df['price'].apply(lambda x: cls._to_float(x, allow_null=True))
        df['parent'] = df['parent'].apply(lambda x: cls._to_int(x, allow_null=True))
        df = df[df['category_id'] > 0].reset_index(drop=True)
        df = cls._replace_nan_with_none(df)
        return df

    @classmethod
    def clean_product_full(cls, csv_bytes: bytes, dt: str) -> pd.DataFrame:
        df = cls._read_csv_auto_encoding(csv_bytes)
        for col in cls.PRODUCT_COLUMNS:
            if col not in df.columns:
                df[col] = ''
        df = df[cls.PRODUCT_COLUMNS].copy()
        df['product_id'] = df['product_id'].apply(lambda x: cls._to_int(x, allow_null=False))
        df['category_id'] = df['category_id'].apply(lambda x: cls._to_int(x, allow_null=False))
        df['name'] = df['name'].apply(cls._to_str)
        df['weight'] = df['weight'].apply(lambda x: cls._to_float(x, allow_null=False))
        df['price'] = df['price'].apply(lambda x: cls._to_float(x, allow_null=True))
        df['change_count'] = df['change_count'].apply(lambda x: cls._to_int(x, allow_null=False))
        df['dt'] = cls._parse_date_str(dt)
        df = df[df['product_id'] > 0].reset_index(drop=True)
        df = cls._replace_nan_with_none(df)
        return df

    @classmethod
    def clean_daily_price(cls, csv_bytes: bytes) -> Tuple[pd.DataFrame, Optional[str]]:
        df = cls._read_csv_auto_encoding(csv_bytes)
        for col in cls.DAILY_PRICE_COLUMNS:
            if col not in df.columns:
                df[col] = ''
        df = df[cls.DAILY_PRICE_COLUMNS].copy()
        df['product_id'] = df['product_id'].apply(lambda x: cls._to_int(x, allow_null=False))
        df['category_id'] = df['category_id'].apply(lambda x: cls._to_int(x, allow_null=False))
        df['name'] = df['name'].apply(cls._to_str)
        df['price'] = df['price'].apply(lambda x: cls._to_float(x, allow_null=True))
        df['change_date'] = df['change_date'].apply(cls._to_date)
        change_dates = df['change_date'].dropna().unique()
        dt_obj = change_dates[0] if len(change_dates) > 0 else None
        dt_str = dt_obj.isoformat() if dt_obj else None
        df = df[df['product_id'] > 0].reset_index(drop=True)
        df = df[df['change_date'].notna()].reset_index(drop=True)
        df = cls._replace_nan_with_none(df)
        return df, dt_str

    @staticmethod
    def parse_daily_price_date(filename: str) -> Optional[str]:
        import re
        match = re.search(r'(\d{8})', filename)
        if match:
            date_str = match.group(1)
            try:
                return datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
            except ValueError:
                pass
        return None

    @staticmethod
    def _replace_nan_with_none(df: pd.DataFrame) -> pd.DataFrame:
        df = df.where(pd.notnull(df), None)
        for col in df.columns:
            df[col] = df[col].astype(object)
        return df

    @staticmethod
    def df_to_csv(df: pd.DataFrame) -> bytes:
        return df.to_csv(index=False).encode('utf-8')