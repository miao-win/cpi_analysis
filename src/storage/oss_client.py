import os
from typing import Optional, BinaryIO, Union
from pathlib import Path

import oss2
from dotenv import load_dotenv


class OSSClient:
    def __init__(
        self,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
        endpoint: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        load_dotenv(override=True)
        self.access_key_id = access_key_id or os.getenv("OSS_ACCESS_KEY_ID")
        self.access_key_secret = access_key_secret or os.getenv("OSS_ACCESS_KEY_SECRET")
        self.endpoint = endpoint or os.getenv("OSS_ENDPOINT")
        self.bucket_name = bucket_name or os.getenv("OSS_BUCKET_NAME")

        self._validate_config()

        self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)

    def _validate_config(self):
        missing = []
        if not self.access_key_id:
            missing.append("OSS_ACCESS_KEY_ID")
        if not self.access_key_secret:
            missing.append("OSS_ACCESS_KEY_SECRET")
        if not self.endpoint:
            missing.append("OSS_ENDPOINT")
        if not self.bucket_name:
            missing.append("OSS_BUCKET_NAME")
        if missing:
            raise ValueError(f"缺少OSS配置项: {', '.join(missing)}")

    def upload_file(
        self,
        local_path: Union[str, Path],
        oss_key: str,
        headers: Optional[dict] = None,
    ) -> str:
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"本地文件不存在: {local_path}")

        self.bucket.put_object_from_file(oss_key, str(local_path), headers=headers)
        return self.get_file_url(oss_key)

    def upload_bytes(
        self,
        data: bytes,
        oss_key: str,
        headers: Optional[dict] = None,
    ) -> str:
        self.bucket.put_object(oss_key, data, headers=headers)
        return self.get_file_url(oss_key)

    def upload_stream(
        self,
        stream: BinaryIO,
        oss_key: str,
        headers: Optional[dict] = None,
    ) -> str:
        self.bucket.put_object(oss_key, stream, headers=headers)
        return self.get_file_url(oss_key)

    def download_file(
        self,
        oss_key: str,
        local_path: Union[str, Path],
    ) -> Path:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.bucket.get_object_to_file(oss_key, str(local_path))
        return local_path

    def download_bytes(self, oss_key: str) -> bytes:
        result = self.bucket.get_object(oss_key)
        return result.read()

    def download_stream(self, oss_key: str) -> BinaryIO:
        result = self.bucket.get_object(oss_key)
        return result

    def delete_file(self, oss_key: str) -> bool:
        try:
            self.bucket.delete_object(oss_key)
            return True
        except Exception:
            return False

    def file_exists(self, oss_key: str) -> bool:
        try:
            self.bucket.head_object(oss_key)
            return True
        except oss2.exceptions.NoSuchKey:
            return False
        except Exception:
            return False

    def list_files(self, prefix: str = "", max_keys: int = 100) -> list:
        results = []
        for obj in oss2.ObjectIteratorV2(self.bucket, prefix=prefix, max_keys=max_keys):
            results.append({
                "key": obj.key,
                "size": obj.size,
                "last_modified": obj.last_modified,
                "etag": obj.etag,
            })
        return results

    def get_file_url(self, oss_key: str, expires: int = 3600) -> str:
        if self.endpoint.startswith("https://") or self.endpoint.startswith("http://"):
            return f"{self.endpoint.rstrip('/')}/{self.bucket_name}/{oss_key.lstrip('/')}"
        return f"https://{self.bucket_name}.{self.endpoint}/{oss_key.lstrip('/')}"

    def get_signed_url(self, oss_key: str, expires: int = 3600) -> str:
        return self.bucket.sign_url("GET", oss_key, expires)
