from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from omega.webhooks import read_bounded_body


class FakeRequest:
    def __init__(self, chunks, headers=None):
        self._chunks = chunks
        self.headers = headers or {}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


def test_bounded_webhook_reader_accepts_small_payload():
    async def check():
        result = await read_bounded_body(FakeRequest([b'{"action":', b'"ping"}']))
        assert result == b'{"action":"ping"}'

    asyncio.run(check())


def test_bounded_webhook_reader_rejects_oversized_content_length():
    async def check():
        with pytest.raises(HTTPException) as exc:
            await read_bounded_body(FakeRequest([], {"content-length": "1001"}), max_bytes=1000)
        assert exc.value.status_code == 413

    asyncio.run(check())


def test_bounded_webhook_reader_rejects_oversized_stream_without_content_length():
    async def check():
        with pytest.raises(HTTPException) as exc:
            await read_bounded_body(FakeRequest([b"a" * 600, b"b" * 500]), max_bytes=1000)
        assert exc.value.status_code == 413

    asyncio.run(check())


def test_bounded_webhook_reader_rejects_invalid_content_length():
    async def check():
        with pytest.raises(HTTPException) as exc:
            await read_bounded_body(FakeRequest([], {"content-length": "invalid"}))
        assert exc.value.status_code == 400

    asyncio.run(check())
