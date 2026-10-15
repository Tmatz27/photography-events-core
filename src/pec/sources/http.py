"""Cancellation-safe bounded reads; trusted origins, no redirect or secret diagnostics."""

import asyncio
import json
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp


class FetchError(ValueError):
    def __init__(self, code, status=502, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)


@dataclass
class Response:
    status: int
    body: dict
    size: int = 0
    retry_after: str | None = None


async def read(url, user_agent, *, session, headers=None):
    try:
        async with session.get(url, allow_redirects=False, headers={
            **(headers or {}), "User-Agent": user_agent,
            "Accept": "application/json,application/geo+json"}) as response:
            if response.status != 200:
                return Response(response.status, {}, 0, response.headers.get('Retry-After'))
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > 16 * 1024 * 1024:
                    raise FetchError("response_too_large")
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeError):
                raise FetchError("invalid_json") from None
            return Response(response.status, body, len(raw))
    except (aiohttp.ClientError, OSError, TimeoutError):
        raise FetchError("network_failure") from None


class Client:
    def __init__(self, contract, user_agent, reserve=None, transport=None):
        if (
            not isinstance(user_agent, str)
            or len(user_agent) < 10
            or any(ord(c) < 32 or ord(c) > 126 for c in user_agent)
        ):
            raise ValueError("Descriptive ASCII User-Agent required")
        self.contract, self.user_agent, self.reserve = contract, user_agent, reserve
        self.transport = transport
        self.requests = self.bytes_received = self.rate_limited = 0
        self.last_request = None
        self.session = None

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def get(self, url, *, headers=None, allow_list=False):
        host = urlparse(self.contract.interface.split(";", 1)[0]).hostname
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != host
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise FetchError("untrusted_pagination_url")
        if self.reserve:
            await self.reserve()
        else:
            # Optional manual verification still follows the recommended pace.
            loop = asyncio.get_running_loop()
            if self.last_request is not None:
                await asyncio.sleep(
                    max(0, self.contract.request_spacing_seconds - (loop.time() - self.last_request))
                )
            self.last_request = loop.time()
            if self.requests >= min(10, self.contract.requests_per_day):
                raise FetchError("manual_request_budget_exhausted", 429)
        self.requests += 1
        if self.transport:
            response = await self.transport(url, self.user_agent)
        else:
            if self.session is None:
                self.session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=20, connect=10, sock_read=10),
                    connector=aiohttp.TCPConnector(limit=1), trust_env=False)
            response = await read(url, self.user_agent, session=self.session, headers=headers)
        self.bytes_received += response.size
        if response.status == 429:
            self.rate_limited += 1
        if response.status != 200:
            raise FetchError("provider_http_failure", response.status, response.retry_after)
        if not isinstance(response.body, dict) and not (allow_list and isinstance(response.body, list)):
            raise FetchError("invalid_page")
        return response.body
