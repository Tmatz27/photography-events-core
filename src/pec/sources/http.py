"""Bounded public reads, descriptive UA, no credentials/redirect/private-coordinate path."""
import asyncio
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class FetchError(ValueError):
    def __init__(self,code,status=502,retry_after=None):
        self.code,self.status,self.retry_after=code,status,retry_after
        super().__init__(code)


@dataclass
class Response:
    status: int
    body: dict
    size: int = 0
    retry_after: str | None = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def read(url,user_agent):
    req=Request(url,headers={"User-Agent":user_agent,"Accept":"application/json,application/geo+json"})
    try:
        with build_opener(NoRedirect()).open(req,timeout=20) as response:
            raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:
                raise FetchError("response_too_large")
            try:
                body=json.loads(raw)
            except (ValueError,UnicodeError):
                raise FetchError("invalid_json") from None
            return Response(response.status,body,len(raw))
    except HTTPError as exc:
        return Response(exc.code,{},0,exc.headers.get("Retry-After"))
    except (URLError,OSError,TimeoutError):
        raise FetchError("network_failure") from None


class Client:
    def __init__(self,contract,user_agent,reserve=None,transport=None):
        if not isinstance(user_agent,str) or len(user_agent)<10 or any(ord(c)<32 or ord(c)>126 for c in user_agent):
            raise ValueError("Descriptive ASCII User-Agent required")
        self.contract,self.user_agent,self.reserve=contract,user_agent,reserve
        self.transport=transport
        self.requests=self.bytes_received=self.rate_limited=0
        self.last_request=None

    async def get(self,url):
        host=urlparse(self.contract.interface.split(";",1)[0]).hostname
        parsed=urlparse(url)
        if parsed.scheme!="https" or parsed.hostname!=host or parsed.username or parsed.password or parsed.port not in (None,443):
            raise FetchError("untrusted_pagination_url")
        if self.reserve:
            await self.reserve()
        else:
            # Optional manual verification still follows the recommended pace.
            loop=asyncio.get_running_loop()
            if self.last_request is not None:
                await asyncio.sleep(max(0,self.contract.request_spacing_seconds-(loop.time()-self.last_request)))
            self.last_request=loop.time()
            if self.requests>=min(10,self.contract.requests_per_day):
                raise FetchError("manual_request_budget_exhausted",429)
        self.requests+=1
        response=await self.transport(url,self.user_agent) if self.transport else await asyncio.to_thread(read,url,self.user_agent)
        self.bytes_received+=response.size
        if response.status==429:
            self.rate_limited+=1
        if response.status!=200:
            raise FetchError("provider_http_failure",response.status,response.retry_after)
        if not isinstance(response.body,dict):
            raise FetchError("invalid_page")
        return response.body
