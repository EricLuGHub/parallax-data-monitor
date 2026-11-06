"""Bounded, metered public HTTP. Budget trips stop requests instead of buffering quotes."""
import asyncio,json,time
from collections import deque
import httpx

class NetworkBudgetExceeded(RuntimeError): pass

class MeteredClient:
    def __init__(self,settings):
        self.limit=settings.get('network_kib_per_second',256)*1024
        self.window=30.0;self.samples=deque();self.total=0;self.requests=0
        self.started=time.monotonic();self.last_request=0;self.last_latency=0;self.errors=0;self.tripped=None
        self.lock=asyncio.Lock();self.client=httpx.AsyncClient(timeout=10,headers={'User-Agent':'ParallaxResearch/0.2','Accept-Encoding':'gzip, deflate'},limits=httpx.Limits(max_connections=4))

    def account(self,n):
        now=time.monotonic();self.samples.append((now,n));self.total+=n
        while self.samples and self.samples[0][0]<now-self.window:self.samples.popleft()
        if sum(x[1] for x in self.samples)>self.limit*self.window:
            self.tripped='30-second receive budget exceeded; collection stopped'
            raise NetworkBudgetExceeded(self.tripped)

    async def get(self,url,params=None):
        if self.tripped:raise NetworkBudgetExceeded(self.tripped)
        async with self.lock:
            await asyncio.sleep(max(0,.25-(time.monotonic()-self.last_request)))
            self.last_request=time.monotonic()
        if self.tripped:raise NetworkBudgetExceeded(self.tripped)
        start=time.monotonic();self.requests+=1
        try:
            async with self.client.stream('GET',url,params=params) as response:
                body=bytearray();downloaded=0
                async for chunk in response.aiter_bytes():
                    self.account(response.num_bytes_downloaded-downloaded);downloaded=response.num_bytes_downloaded
                    body.extend(chunk)
                    if len(body)>12*1024**2:
                        self.tripped='Response exceeds 12 MiB; collection stopped'
                        raise NetworkBudgetExceeded(self.tripped)
                result=httpx.Response(response.status_code,content=bytes(body),request=response.request)
                result.raise_for_status()
                return result
        except Exception:
            self.errors+=1;raise
        finally:self.last_latency=time.monotonic()-start

    def summary(self):
        now=time.monotonic()
        while self.samples and self.samples[0][0]<now-self.window:self.samples.popleft()
        return {'received_bytes':self.total,'receive_kib_s':round(sum(x[1] for x in self.samples)/min(self.window,max(1,now-self.started))/1024,2),
                'budget_kib_s':self.limit/1024,'requests':self.requests,'errors':self.errors,'last_latency_ms':round(self.last_latency*1000),
                'stopped_reason':self.tripped,'measurement':'HTTP compressed payload; excludes TLS/header overhead; 30s circuit breaker, not a router traffic shaper'}

    async def aclose(self):await self.client.aclose()
