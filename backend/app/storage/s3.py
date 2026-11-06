"""The S3 object store. RustFS (``docker compose``, integration tests) speaks the same API, so
it is this adapter with another endpoint and static keys."""

import asyncio
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.storage.port import ObjectNotFoundError, attachment_disposition

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_MISSING = {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}


def _client(
    endpoint_url: str | None,
    *,
    region: str,
    access_key_id: str | None,
    secret_access_key: str | None,
) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        # Path-style addressing works for RustFS and S3 alike, and keeps the bucket in the path.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


class S3ObjectStore:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        public_endpoint_url: str | None,
        region: str,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> None:
        self.bucket = bucket
        keys = {"access_key_id": access_key_id, "secret_access_key": secret_access_key}
        self._client = _client(endpoint_url, region=region, **keys)
        # Presigned URLs are signed for the address the browser uses, which can differ from
        # the one the API reaches the store at (a container hostname, say).
        self._presigner = _client(public_endpoint_url or endpoint_url, region=region, **keys)

    async def prepare(self) -> None:
        """Creates the bucket if it doesn't exist yet (RustFS starts empty)."""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in _MISSING:
                raise
            await asyncio.to_thread(self._client.create_bucket, Bucket=self.bucket)

    def presign_put(self, key: str, *, content_type: str, expires_in: int) -> str:
        url: str = self._presigner.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )
        return url

    def presign_get(self, key: str, *, filename: str, content_type: str, expires_in: int) -> str:
        url: str = self._presigner.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": attachment_disposition(filename),
            },
            ExpiresIn=expires_in,
        )
        return url

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in _MISSING:
                raise ObjectNotFoundError(key) from None
            raise
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def size(self, key: str) -> int:
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self.bucket, Key=key
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in _MISSING:
                raise ObjectNotFoundError(key) from None
            raise
        return response["ContentLength"]

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)
