# -*- coding: utf-8 -*-
"""
pytest公共fixtures
"""
import os
import sys

import pytest

# 保证能从项目根目录导入src包
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def category_csv_bytes():
    path = os.path.join(FIXTURES_DIR, 'categories.csv')
    with open(path, 'rb') as f:
        return f.read()


@pytest.fixture
def product_csv_bytes():
    path = os.path.join(FIXTURES_DIR, 'products.csv')
    with open(path, 'rb') as f:
        return f.read()


@pytest.fixture
def daily_price_csv_bytes():
    path = os.path.join(FIXTURES_DIR, 'daily_prices.csv')
    with open(path, 'rb') as f:
        return f.read()


@pytest.fixture
def sample_date():
    return '2025-05-17'
