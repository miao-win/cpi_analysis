#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

from src.storage.clickhouse_client import ClickHouseClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

INDEX_TYPES = ['laspeyres', 'paasche', 'fisher']
INDEX_TYPE_NAMES = {
    'laspeyres': '拉氏指数',
    'paasche': '派氏指数',
    'fisher': '费雪指数'
}
INDEX_TYPE_COLORS = {
    'laspeyres': '#1f77b4',
    'paasche': '#ff7f0e',
    'fisher': '#2ca02c'
}


class DataVisualizer:
    def __init__(self, ck_client: Optional[ClickHouseClient] = None, output_dir: str = 'output'):
        self.ck = ck_client or ClickHouseClient()
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def get_index_data(
        self,
        index_level: Optional[str] = 'total',
        category_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        index_types: Optional[List[str]] = None
    ) -> pd.DataFrame:
        if index_types is None:
            index_types = INDEX_TYPES

        conditions = []
        params: Dict[str, Any] = {}

        if index_level is not None:
            conditions.append("index_level = {level:String}")
            params['level'] = index_level

        if category_id is not None:
            conditions.append("category_id = {cat_id:UInt64}")
            params['cat_id'] = category_id

        if start_date:
            conditions.append("date >= {start_date:Date}")
            params['start_date'] = start_date

        if end_date:
            conditions.append("date <= {end_date:Date}")
            params['end_date'] = end_date

        if index_types:
            escaped_types = ', '.join([f"'{t}'" for t in index_types])
            conditions.append(f"index_type IN ({escaped_types})")

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT date, index_level, category_id, category_name, index_type, index_value, base_date
        FROM index_result
        WHERE {where_clause}
        ORDER BY date, index_type
        """

        with self.ck:
            result = self.ck.query_dicts(query, parameters=params)

        if not result:
            logger.warning("No index data found for the given criteria.")
            return pd.DataFrame()

        df = pd.DataFrame(result)
        df['date'] = pd.to_datetime(df['date'])
        df['base_date'] = pd.to_datetime(df['base_date'])

        type_counts = df['index_type'].value_counts().to_dict()
        logger.info("Fetched %d rows, index_type distribution: %s", len(df), type_counts)
        return df

    def plot_index_trend(
        self,
        df: pd.DataFrame,
        title: Optional[str] = None,
        save_path: Optional[str] = None,
        show: bool = True,
        figsize: tuple = (12, 6),
        dpi: int = 100
    ) -> Figure:
        if df.empty:
            raise ValueError("DataFrame is empty, cannot plot.")

        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

        categories = []
        if 'category_id' in df.columns and 'category_name' in df.columns:
            cat_pairs = df[['category_id', 'category_name']].drop_duplicates()
            for _, row in cat_pairs.iterrows():
                categories.append((row['category_id'], row['category_name']))

        if len(categories) <= 1:
            for idx_type in INDEX_TYPES:
                type_data = df[df['index_type'] == idx_type]
                if not type_data.empty:
                    ax.plot(
                        type_data['date'],
                        type_data['index_value'],
                        label=INDEX_TYPE_NAMES.get(idx_type, idx_type),
                        color=INDEX_TYPE_COLORS.get(idx_type),
                        linewidth=2,
                        marker='o',
                        markersize=3
                    )
        else:
            for idx_type in INDEX_TYPES:
                type_data = df[df['index_type'] == idx_type]
                if not type_data.empty:
                    pivot = type_data.pivot(index='date', columns='category_name', values='index_value')
                    for col in pivot.columns:
                        ax.plot(
                            pivot.index,
                            pivot[col],
                            label=f"{col} - {INDEX_TYPE_NAMES.get(idx_type, idx_type)}",
                            marker='o',
                            markersize=2,
                            linewidth=1.5
                        )

        ax.axhline(y=1.0, color='red', linestyle='--', alpha=0.5, label='基准线 (1.0)')

        base_date = df['base_date'].iloc[0]
        ax.axvline(x=base_date, color='gray', linestyle=':', alpha=0.7, label=f'基期: {base_date.strftime("%Y-%m-%d")}')

        if title is None:
            if len(categories) == 1 and categories[0][0] == 0:
                title = '电商高频价格指数 - 总指数趋势'
            elif len(categories) == 1:
                title = f'电商高频价格指数 - {categories[0][1]} 分类指数趋势'
            else:
                title = '电商高频价格指数 - 分类指数趋势'

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('指数值', fontsize=12)

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()

        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc='best', fontsize=10, ncol=min(3, len(ax.get_legend_handles_labels()[0])))

        plt.tight_layout()

        if save_path:
            if not os.path.isabs(save_path):
                save_path = os.path.join(self.output_dir, save_path)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            plt.savefig(save_path, dpi=dpi, bbox_inches='tight')
            logger.info(f"Plot saved to: {save_path}")

        if show:
            plt.show()

        return fig

    def plot_total_index(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        index_types: Optional[List[str]] = None,
        save_path: Optional[str] = None,
        show: bool = True
    ) -> Figure:
        logger.info("Fetching total index data...")
        df = self.get_index_data(
            index_level='total',
            start_date=start_date,
            end_date=end_date,
            index_types=index_types
        )
        return self.plot_index_trend(df, title='电商高频价格指数 - 总指数日度趋势', save_path=save_path, show=show)

    def plot_category_index(
        self,
        category_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        index_types: Optional[List[str]] = None,
        save_path: Optional[str] = None,
        show: bool = True
    ) -> Figure:
        logger.info(f"Fetching category index data for category_id={category_id}...")
        df = self.get_index_data(
            index_level='category',
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
            index_types=index_types
        )
        cat_name = df['category_name'].iloc[0] if not df.empty else f'Category_{category_id}'
        return self.plot_index_trend(
            df,
            title=f'电商高频价格指数 - {cat_name} 分类指数日度趋势',
            save_path=save_path,
            show=show
        )

    def plot_all_categories_comparison(
        self,
        index_type: str = 'fisher',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        top_n: Optional[int] = None,
        save_path: Optional[str] = None,
        show: bool = True
    ) -> Figure:
        logger.info(f"Fetching all category indices for comparison (index_type={index_type})...")
        df = self.get_index_data(
            index_level='category',
            start_date=start_date,
            end_date=end_date,
            index_types=[index_type]
        )

        if top_n:
            latest_date = df['date'].max()
            latest_data = df[df['date'] == latest_date]
            top_cats = latest_data.nlargest(top_n, 'index_value')['category_id'].tolist()
            df = df[df['category_id'].isin(top_cats)]

        return self.plot_index_trend(
            df,
            title=f'电商高频价格指数 - 各分类指数对比 ({INDEX_TYPE_NAMES.get(index_type, index_type)})',
            save_path=save_path,
            show=show
        )

    def export_to_csv(
        self,
        df: pd.DataFrame,
        filename: Optional[str] = None,
        index: bool = False,
        encoding: str = 'utf-8-sig'
    ) -> str:
        if df.empty:
            raise ValueError("DataFrame is empty, cannot export.")

        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'index_result_{timestamp}.csv'

        if not os.path.isabs(filename):
            filename = os.path.join(self.output_dir, filename)

        os.makedirs(os.path.dirname(filename), exist_ok=True)
        df.to_csv(filename, index=index, encoding=encoding)
        logger.info(f"Data exported to CSV: {filename}")
        return filename

    def export_to_excel(
        self,
        df: pd.DataFrame,
        filename: Optional[str] = None,
        sheet_name: str = 'index_result',
        index: bool = False
    ) -> str:
        if df.empty:
            raise ValueError("DataFrame is empty, cannot export.")

        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'index_result_{timestamp}.xlsx'

        if not os.path.isabs(filename):
            filename = os.path.join(self.output_dir, filename)

        os.makedirs(os.path.dirname(filename), exist_ok=True)
        df.to_excel(filename, sheet_name=sheet_name, index=index, engine='openpyxl')
        logger.info(f"Data exported to Excel: {filename}")
        return filename

    def export_all_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        format: str = 'csv',
        filename: Optional[str] = None
    ) -> str:
        logger.info("Fetching all index data for export...")
        df = self.get_index_data(index_level=None, start_date=start_date, end_date=end_date)

        if format.lower() == 'csv':
            return self.export_to_csv(df, filename=filename)
        elif format.lower() in ['excel', 'xlsx', 'xls']:
            return self.export_to_excel(df, filename=filename)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'csv' or 'excel'.")

    def get_available_categories(self) -> List[Dict[str, Any]]:
        with self.ck:
            return self.ck.query_dicts("""
                SELECT DISTINCT category_id, category_name
                FROM index_result
                WHERE index_level = 'category'
                ORDER BY category_id
            """)

    def get_date_range(self) -> Dict[str, str]:
        with self.ck:
            result = self.ck.query_one("""
                SELECT MIN(date) as min_date, MAX(date) as max_date
                FROM index_result
            """)
            if result:
                return {
                    'min_date': str(result[0]) if result[0] else None,
                    'max_date': str(result[1]) if result[1] else None
                }
            return {'min_date': None, 'max_date': None}
