from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from ..models import Source
from ..schemas import IncidentCandidate


class AdapterError(RuntimeError):
    pass


class AdapterConfigurationError(AdapterError):
    pass


@dataclass(frozen=True)
class AdapterResponse:
    body: bytes
    content_type: str
    status_code: int
    headers: dict[str, str]


class BaseAdapter(ABC):
    max_response_bytes = 4 * 1024 * 1024
    snapshot_mode = False

    @abstractmethod
    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        raise NotImplementedError

    async def request_bytes(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        response = await self.request_with_metadata(
            method,
            url,
            params=params,
            headers=headers,
            json_payload=json_payload,
        )
        return response.body, response.content_type

    async def request_with_metadata(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
        allow_not_modified: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> AdapterResponse:
        request_headers = {
            "User-Agent": "AapadSnehi/0.1 (disaster-response research prototype)",
            **(headers or {}),
        }
        if client is not None:
            return await self._request_with_client(
                client,
                method,
                url,
                params=params,
                headers=request_headers,
                json_payload=json_payload,
                allow_not_modified=allow_not_modified,
            )
        async with self.create_http_client() as owned_client:
            return await self._request_with_client(
                owned_client,
                method,
                url,
                params=params,
                headers=request_headers,
                json_payload=json_payload,
                allow_not_modified=allow_not_modified,
            )

    def create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=12.0,
            follow_redirects=False,
        )

    async def _request_with_client(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None,
        headers: dict[str, str],
        json_payload: dict[str, Any] | None,
        allow_not_modified: bool,
    ) -> AdapterResponse:
        async with client.stream(
            method,
            url,
            params=params,
            headers=headers,
            json=json_payload,
        ) as response:
            if response.status_code != 304 or not allow_not_modified:
                response.raise_for_status()
            content_length = int(response.headers.get("content-length", "0") or 0)
            if content_length > self.max_response_bytes:
                raise AdapterError("Provider response exceeded the configured size limit")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > self.max_response_bytes:
                    raise AdapterError("Provider response exceeded the configured size limit")
        return AdapterResponse(
            body=bytes(body),
            content_type=response.headers.get("content-type", ""),
            status_code=response.status_code,
            headers=dict(response.headers),
        )

    @staticmethod
    def _decode_json(body: bytes) -> dict:
        try:
            payload = httpx.Response(200, content=body).json()
        except ValueError as exc:
            raise AdapterError("Provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterError("Provider returned an unexpected JSON shape")
        return payload

    async def get_json(self, url: str, *, params: dict[str, str] | None = None) -> dict:
        body, _ = await self.request_bytes("GET", url, params=params)
        return self._decode_json(body)

    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_payload: dict[str, Any],
    ) -> dict:
        body, _ = await self.request_bytes(
            "POST",
            url,
            headers=headers,
            json_payload=json_payload,
        )
        return self._decode_json(body)

    async def get_text(self, url: str) -> tuple[str, str]:
        body, content_type = await self.request_bytes("GET", url)
        return body.decode("utf-8", errors="replace"), content_type
