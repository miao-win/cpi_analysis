import os
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from clickhouse_connect.driver.query import QueryResult
from dotenv import load_dotenv


class ClickHouseClient:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        **kwargs,
    ):
        load_dotenv(override=True)
        self.host = host or os.getenv("CK_HOST")
        self.port = int(port or os.getenv("CK_PORT", 8123))
        self.user = user or os.getenv("CK_USER", "default")
        self.password = password or os.getenv("CK_PASSWORD", "")
        self.database = database or os.getenv("CK_DATABASE", "default")
        self.kwargs = kwargs

        self._validate_config()
        self._client: Optional[Client] = None

    def _validate_config(self):
        if not self.host:
            raise ValueError("缺少ClickHouse配置项: CK_HOST")

    def connect(self) -> Client:
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                database=self.database,
                **self.kwargs,
            )
        return self._client

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def ping(self) -> bool:
        try:
            client = self.connect()
            return client.ping()
        except Exception:
            return False

    def execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        client = self.connect()
        return client.query(query, parameters=parameters, settings=settings)

    def query_all(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple]:
        result = self.execute(query, parameters=parameters, settings=settings)
        return result.result_rows

    def query_dicts(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        result = self.execute(query, parameters=parameters, settings=settings)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    def query_one(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple]:
        rows = self.query_all(query, parameters=parameters, settings=settings)
        return rows[0] if rows else None

    def query_value(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Any:
        row = self.query_one(query, parameters=parameters, settings=settings)
        return row[0] if row else None

    def execute_command(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        client = self.connect()
        return client.command(query, parameters=parameters, settings=settings)

    def insert(
        self,
        table: str,
        data: List[List[Any]],
        column_names: Optional[List[str]] = None,
        database: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
    ):
        client = self.connect()
        client.insert(
            table=table,
            data=data,
            column_names=column_names,
            database=database or self.database,
            settings=settings,
        )

    def insert_df(
        self,
        table: str,
        df,
        database: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
    ):
        client = self.connect()
        client.insert_df(
            table=table,
            df=df,
            database=database or self.database,
            settings=settings,
        )

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return f"`{identifier.replace('`', '``')}`"

    def table_exists(self, table: str, database: Optional[str] = None) -> bool:
        db = database or self.database
        db_quoted = self._quote_identifier(db)
        table_quoted = self._quote_identifier(table)
        query = f"EXISTS TABLE {db_quoted}.{table_quoted}"
        return bool(self.query_value(query))

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        db = database or self.database
        db_quoted = self._quote_identifier(db)
        query = f"SHOW TABLES FROM {db_quoted}"
        result = self.query_all(query)
        return [row[0] for row in result]

    def get_table_schema(
        self, table: str, database: Optional[str] = None
    ) -> List[Dict[str, str]]:
        db = database or self.database
        db_quoted = self._quote_identifier(db)
        table_quoted = self._quote_identifier(table)
        query = f"DESCRIBE TABLE {db_quoted}.{table_quoted}"
        result = self.query_dicts(query)
        return result

    def create_database(self, database: str, if_not_exists: bool = True):
        if_exists_sql = "IF NOT EXISTS" if if_not_exists else ""
        db_quoted = self._quote_identifier(database)
        self.execute_command(f"CREATE DATABASE {if_exists_sql} {db_quoted}")

    def drop_database(self, database: str, if_exists: bool = True):
        if_exists_sql = "IF EXISTS" if if_exists else ""
        db_quoted = self._quote_identifier(database)
        self.execute_command(f"DROP DATABASE {if_exists_sql} {db_quoted}")

    @contextmanager
    def transaction(self):
        client = self.connect()
        try:
            client.command("BEGIN")
            yield self
            client.command("COMMIT")
        except Exception as e:
            client.command("ROLLBACK")
            raise e
