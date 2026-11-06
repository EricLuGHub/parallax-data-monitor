"""All-symbol quote screening with fair, rate-bounded depth confirmation."""
import asyncio,time,logging
from decimal import Decimal as D
from .adapters import discover_bybit,discover_gate,BYBIT,GATE
from .models import Book
from .identity import index_evidence
from .paper import threshold
from .network import MeteredClient,NetworkBudgetExceeded

log=logging.getLogger(__name__)

class Feeds:
    def __init__(self,engine):
        self.e=engine;self.client=MeteredClient(engine.settings);self.e.network=self.client
        self.tickers={};self.candidates={};self.checked={};self.turn=0;self.tasks=[]
        self.last_discovery=0;self.identity_checked={};self.screen_active={}

    async def json(self,url,params=None):
        result=(await self.client.get(url,params)).json()
        if isinstance(result,dict) and result.get('retCode',0)!=0:raise ValueError(result.get('retMsg'))
        return result

    async def discover(self):
        for venue,fn in [('bybit',discover_bybit),('gate',discover_gate)]:
            self.e.venue_status.setdefault(venue,{'state':'discovering','markets':0})
            try:
                markets,excluded=await fn(self.client)
                old={k:m for k,m in self.e.markets.items() if m.venue==venue}
                new={m.key:m for m in markets}
                self.e.invalidate(list(set(old)-set(new)),'market_removed')
                for k in old:self.e.markets.pop(k,None)
                self.e.markets.update(new)
                self.e.excluded=[x for x in self.e.excluded if x['venue']!=venue]+excluded
                self.e.venue_status[venue].update(state='screening',markets=len(markets),error=None)
            except NetworkBudgetExceeded:raise
            except Exception as exc:
                self.e.venue_status[venue].update(state='error',error=str(exc)[:200])
        self.e.catalog(list(self.e.markets.values()));self.last_discovery=time.monotonic()

    async def quote_group(self,venue,kind):
        try:
            start=time.time()
            if venue=='bybit':
                result=await self.json(BYBIT+'/v5/market/tickers',{'category':'spot' if kind=='spot' else 'linear'})
                rows=result['result']['list']
            else:
                rows=await self.json(GATE+('/spot/tickers' if kind=='spot' else '/futures/usdt/tickers'))
            now=time.time()
            self.e.recorder.emit('screen_quotes',{'venue':venue,'kind':kind,'requested_at':start,'received_at':now,'rows':rows},raw=True)
            # Replace the entire group: missing symbols must not retain previous quotes.
            for key in list(self.tickers):
                if key.startswith(f'{venue}:{kind}:'):self.tickers.pop(key)
            for x in rows:
                symbol=x.get('symbol') if venue=='bybit' else x.get('currency_pair' if kind=='spot' else 'contract')
                key=f'{venue}:{kind}:{symbol}'
                if key not in self.e.markets:continue
                bid=x.get('bid1Price') if venue=='bybit' else x.get('highest_bid')
                ask=x.get('ask1Price') if venue=='bybit' else x.get('lowest_ask')
                if not bid or not ask:continue
                bid,ask=D(bid),D(ask)
                if not bid.is_finite() or not ask.is_finite() or bid<=0 or ask<=bid:continue
                self.tickers[key]={'bid':bid,'ask':ask,'at':now,'request_started':start}
                if kind=='perp':
                    self.e.funding[key]={'rate':x.get('fundingRate') if venue=='bybit' else x.get('funding_rate'),
                        'at':now,'next_time':x.get('nextFundingTime'),'interval_hours':float(x.get('fundingIntervalHour') or 0) or self.e.markets[key].funding_interval_hours}
            self.e.venue_status[venue].update(state='screening',last_message=now,error=None)
        except NetworkBudgetExceeded:raise
        except Exception as exc:
            for key in list(self.tickers):
                if key.startswith(f'{venue}:{kind}:'):self.tickers.pop(key)
            self.e.venue_status[venue].update(state='error',error=str(exc)[:200])
            self.e.recorder.emit('screen_error',{'venue':venue,'kind':kind,'error':str(exc)})

    def screen(self):
        now=time.time();s=self.e.settings;self.candidates={};screened=0
        for rid,r in self.e.routes.items():
            a=self.tickers.get(r['buy']['key']);b=self.tickers.get(r['short']['key'])
            if not a or not b or now-min(a['request_started'],b['request_started'])>s.get('screen_stale_seconds',15):continue
            screened+=1;gap=float((b['bid']/a['ask']-1)*10000)
            # Best-price/full-budget upper bound. Below it, depth walking cannot improve profit.
            sf=s['spot_fee_bps']/10000;pf=s['perp_fee_bps']/10000;exit_gap=s['exit_gap_bps']/10000
            budget=s['trade_cad']/s['cad_per_usdt']
            upper_net=budget*(gap/10000*(1-pf)-2*sf-pf*(2+exit_gap)-exit_gap-(s['execution_buffer_bps']+s['holding_cost_bps'])/10000)
            if upper_net>=threshold(s):self.candidates[rid]={'gap_bps':gap,'at':now,'upper_net':upper_net}
            qualifies=rid in self.candidates
            if qualifies:
                if rid not in self.screen_active:
                    self.screen_active[rid]={'id':rid,'base':r['base'],'started_at':now,'last_seen':now,'interval_seconds':s.get('screen_interval_seconds',5),'kind':'polled quote upper bound; not depth verified'}
                    self.e.recorder.emit('screen_episode_start',self.screen_active[rid],rid)
                self.screen_active[rid]['last_seen']=now
            if rid not in self.e.results or self.e.results[rid].get('status') in ('invalid_book','stale_feed','screen_only','screen_gap'):
                self.e.results[rid]={**r,'status':'screen_gap' if qualifies else 'screen_only','screen_gap_bps':gap,'screened_at':now}
        for rid in set(self.screen_active)-set(self.candidates):
            ep=self.screen_active.pop(rid)
            ep.update(ended_at=now,duration=ep['last_seen']-ep['started_at'],reason='screen_no_longer_qualifies_or_missing')
            self.e.recorder.emit('screen_episode_end',ep,rid)
        self.e.screening={'interval_seconds':s.get('screen_interval_seconds',5),'screened_routes':screened,'queued_routes':len(self.candidates),
            'last_scan':now,'mode':'all-symbol quotes; bounded depth queue; brief gaps can be missed'}

    def next_route(self):
        self.turn+=1
        positions=set(self.e.paper)|set(self.e.pending)
        candidates=set(self.candidates)|set(self.e.active)
        # Four out of five turns monitor existing exposure; the fifth keeps discovery moving.
        pool=positions if positions and (self.turn%5 or not candidates-positions) else candidates-positions
        if not pool:pool=positions
        pool={rid for rid in pool if rid in self.e.routes}
        if not pool:return None
        return min(pool,key=lambda rid:(self.checked.get(rid,0),rid))

    async def depth(self,key):
        market=self.e.markets[key];start=time.time()
        if market.venue=='bybit':
            response=await self.json(BYBIT+'/v5/market/orderbook',{'category':'spot' if market.kind=='spot' else 'linear','symbol':market.symbol,'limit':50})
            d=response['result'];bids=d['b'];asks=d['a'];sequence=d.get('u',0);exchange_ms=d.get('ts',0)
            server_ms=response.get('time',exchange_ms)
        else:
            spot=market.kind=='spot'
            d=await self.json(GATE+('/spot/order_book' if spot else '/futures/usdt/order_book'),
                {('currency_pair' if spot else 'contract'):market.symbol,'limit':50,'with_id':'true'})
            bids=d['bids'];asks=d['asks'];sequence=d.get('id',0)
            exchange_ms=float(d.get('update',0))*(1 if spot else 1000)
            server_ms=float(d.get('current',0))*(1 if spot else 1000)
        now=time.time()
        if now-start>self.e.settings.get('max_depth_rtt_seconds',2):raise ValueError('slow depth response')
        if server_ms and abs(now-server_ms/1000)>self.e.settings['stale_seconds']:raise ValueError('stale response timestamp / clock skew')
        book=Book();book.apply(bids,asks,True,sequence,exchange_ms,market.multiplier,50)
        if not book.valid:raise ValueError('invalid depth')
        # A current REST snapshot confirms unchanged quiet levels; use request start conservatively.
        book.received=start;book.mono=time.monotonic()-(now-start)
        self.e.recorder.emit('depth_snapshot',{'key':key,'requested_at':start,'received_at':now,'response':d},key,raw=True)
        return book

    async def confirm(self,rid):
        r=self.e.routes[rid];keys=[r['buy']['key'],r['short']['key']]
        self.checked[rid]=time.monotonic()
        results=await asyncio.gather(*(self.depth(k) for k in keys),return_exceptions=True)
        for result in results:
            if isinstance(result,NetworkBudgetExceeded):raise result
        if any(isinstance(result,BaseException) for result in results):
            self.e.invalidate(keys,'depth_request_failed')
            return
        # Publish both snapshots atomically; never combine one new leg with an old counterpart.
        for key,book in zip(keys,results):self.e.books[key]=book;self.e.messages+=1;self.e.dirty.update(self.e.by_market[key])
        self.e.evaluate(rid)

    async def screens(self):
        while True:
            started=time.monotonic()
            if started-self.last_discovery>900:await self.discover()
            results=await asyncio.gather(*(self.quote_group(v,k) for v in ('bybit','gate') for k in ('spot','perp')),return_exceptions=True)
            for r in results:
                if isinstance(r,BaseException):raise r
            self.screen()
            await asyncio.sleep(max(.1,self.e.settings.get('screen_interval_seconds',5)-(time.monotonic()-started)))

    async def depths(self):
        while True:
            started=time.monotonic();rid=self.next_route()
            if rid:await self.confirm(rid)
            await asyncio.sleep(max(.1,self.e.settings.get('depth_route_interval_seconds',1)-(time.monotonic()-started)))

    async def identities(self):
        while True:
            eligible=[rid for rid,r in self.e.routes.items() if r['buy']['venue']=='gate' and r['short']['venue']=='bybit'
                      and time.time()-self.identity_checked.get(rid,0)>900]
            if eligible:
                rid=min(eligible,key=lambda k:(k not in self.candidates,self.identity_checked.get(k,0),k))
                r=self.e.routes[rid];self.identity_checked[rid]=time.time()
                try:
                    response=await self.json(BYBIT+'/v5/market/index-price-components',{'indexName':r['short']['symbol']})
                    evidence=index_evidence(r,response,time.time())
                    self.e.recorder.emit('identity_index',{'id':rid,'response':response},rid)
                    if evidence:
                        currency=await self.json(GATE+'/spot/currencies/'+r['base'])
                        if currency.get('currency')!=r['base'] or currency.get('trade_disabled') or currency.get('delisted') or any(str(c.get('addr','')).startswith('invalid-') for c in currency.get('chains',[])):
                            evidence=None
                        else:evidence['spot_currency']=currency
                    self.e.recorder.emit('identity_check',{'id':rid,'evidence':evidence},rid)
                    if evidence:
                        self.e.settings.setdefault('identity_routes',{})[rid]=evidence
                        r.update(identity='reviewed',identity_evidence=evidence)
                        self.e.dirty.add(rid)
                    else:
                        self.e.settings.setdefault('identity_routes',{}).pop(rid,None)
                        r.update(identity='symbol match — unverified',identity_evidence=None)
                except NetworkBudgetExceeded:raise
                except Exception as exc:
                    self.e.recorder.emit('identity_error',{'id':rid,'error':str(exc)},rid)
            await asyncio.sleep(2)

    async def run(self):
        try:
            await self.discover()
            self.tasks=[asyncio.create_task(self.screens()),asyncio.create_task(self.depths()),asyncio.create_task(self.identities())]
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:raise
        except Exception as exc:
            for task in self.tasks:task.cancel()
            await asyncio.gather(*self.tasks,return_exceptions=True)
            self.e.invalidate(list(self.e.books),'collector_stopped')
            for v in self.e.venue_status.values():v.update(state='stopped',error=str(exc)[:200])
            self.e.recorder.emit('collector_stopped',{'reason':str(exc)})
            log.exception('Collection stopped')

    async def close(self):
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.client.aclose()
