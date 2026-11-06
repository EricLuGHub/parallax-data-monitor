"""Public market data only. No authenticated endpoints or order placement."""
import asyncio,json,logging,random,time
from decimal import Decimal as D
import httpx
from websockets.asyncio.client import connect
from .models import Market

log=logging.getLogger(__name__)
BYBIT='https://api.bybit.com'
GATE='https://api.gateio.ws/api/v4'

async def get(client,url,params=None):
    for attempt in range(4):
        try:
            response=await client.get(url,params=params);response.raise_for_status();d=response.json()
            if isinstance(d,dict) and d.get('retCode',0)!=0:raise ValueError(d.get('retMsg'))
            return d
        except (httpx.HTTPError,ValueError):
            if attempt==3:raise
            await asyncio.sleep(2**attempt)

async def discover_bybit(client):
    markets=[];excluded=[]
    for category,kind in [('spot','spot'),('linear','perp')]:
        cursor='';seen=set()
        while True:
            params={'category':category}
            if category=='linear':params['limit']=1000
            if cursor:params['cursor']=cursor
            data=(await get(client,BYBIT+'/v5/market/instruments-info',params))['result']
            for x in data['list']:
                if x['quoteCoin']!='USDT' or x['status']!='Trading' or (kind=='perp' and x.get('contractType')!='LinearPerpetual'):
                    excluded.append({'venue':'bybit','symbol':x['symbol'],'reason':'not active USDT spot/linear perpetual'});continue
                lot=x['lotSizeFilter'];base=x['baseCoin']
                # Never guess whether a numeric prefix denotes a token or a contract multiplier.
                if base[0].isdigit():
                    excluded.append({'venue':'bybit','symbol':x['symbol'],'reason':'numeric asset identity needs explicit mapping'});continue
                markets.append(Market('bybit',kind,x['symbol'],base,
                    D(lot.get('qtyStep',lot.get('basePrecision','0.00000001'))),D(lot.get('minOrderQty','0')),
                    D(lot.get('minNotionalValue',lot.get('minOrderAmt','0'))),D(x['priceFilter']['tickSize']),
                    funding_interval_hours=float(x.get('fundingInterval',0))/60 or None,
                    url=(f'https://www.bybit.com/en/trade/spot/{base}/USDT' if kind=='spot' else f'https://www.bybit.com/trade/usdt/{x["symbol"]}')))
            cursor=data.get('nextPageCursor','')
            if not cursor or cursor in seen:break
            seen.add(cursor)
    return markets,excluded

async def discover_gate(client):
    markets=[];excluded=[]
    spot,perp=await asyncio.gather(get(client,GATE+'/spot/currency_pairs'),get(client,GATE+'/futures/usdt/contracts'))
    for x in spot:
        if x['quote']!='USDT' or x.get('trade_status')!='tradable':
            excluded.append({'venue':'gate','symbol':x['id'],'reason':'not active USDT spot'});continue
        base=x['base']
        if base[0].isdigit():
            excluded.append({'venue':'gate','symbol':x['id'],'reason':'numeric asset identity needs explicit mapping'});continue
        markets.append(Market('gate','spot',x['id'],base,D(10)**-int(x['amount_precision']),D(x.get('min_base_amount') or '0'),
            D(x.get('min_quote_amount') or '0'),D(10)**-int(x['precision']),url=f'https://www.gate.com/trade/{x["id"]}'))
    for x in perp:
        if x.get('in_delisting') or x.get('status','trading')!='trading' or x.get('is_pre_market') or not x['name'].endswith('_USDT'):
            excluded.append({'venue':'gate','symbol':x['name'],'reason':'delisting / unsupported settlement'});continue
        base=x['name'][:-5]
        if base[0].isdigit():
            excluded.append({'venue':'gate','symbol':x['name'],'reason':'numeric asset identity needs explicit mapping'});continue
        mul=D(x['quanto_multiplier'])
        markets.append(Market('gate','perp',x['name'],base,mul,mul*D(str(x.get('order_size_min',1))),D(0),
            D(x['order_price_round']),mul,funding_rate=x.get('funding_rate'),
            funding_interval_hours=float(x.get('funding_interval',28800))/3600,
            url=f'https://www.gate.com/futures/USDT/{x["name"]}'))
    return markets,excluded

class Feeds:
    def __init__(self,engine):
        self.e=engine;self.tasks=[];self.client=None;self.running=False;self.heartbeats={};self.reconnects=0

    async def run(self):
        async with httpx.AsyncClient(timeout=30,headers={'User-Agent':'ParallaxResearch/0.1'}) as client:
            self.client=client
            for venue,discover in [('bybit',discover_bybit),('gate',discover_gate)]:
                self.e.venue_status[venue]={'state':'discovering','error':None}
            while True:
                changed=False
                for venue,discover in [('bybit',discover_bybit),('gate',discover_gate)]:
                    try:
                        markets,excluded=await discover(client)
                        old={k:v.public() for k,v in self.e.markets.items() if v.venue==venue}
                        new={m.key:m.public() for m in markets}
                        if new!=old:
                            # Mark removed books invalid before route catalog replacement.
                            self.e.invalidate(list(set(old)-set(new)),'market_removed')
                            for k in old:self.e.markets.pop(k,None)
                            self.e.markets.update({m.key:m for m in markets});changed=True
                        self.e.excluded=[x for x in self.e.excluded if x['venue']!=venue]+excluded
                        self.e.venue_status[venue].update(state='catalog_ready',markets=len(markets),discovered_at=time.time(),error=None)
                    except Exception as exc:
                        self.e.venue_status[venue].update(state='error',error=str(exc)[:250]);log.exception('Discovery %s',venue)
                if changed or not self.tasks:
                    for task in self.tasks:task.cancel()
                    await asyncio.gather(*self.tasks,return_exceptions=True);self.tasks=[]
                    for rid in list(self.e.active):self.e.fail(rid,'invalid_book',time.time())
                    self.e.invalidate(list(self.e.books),'catalog_refresh')
                    self.e.catalog(list(self.e.markets.values()))
                    used=set(self.e.by_market)
                    for venue in ('bybit','gate'):
                        for kind in ('spot','perp'):
                            markets=[m for m in self.e.markets.values() if m.venue==venue and m.kind==kind and m.key in used]
                            # Shards cover ALL supported markets; there is no coin-count sampling.
                            for i in range(0,len(markets),100):
                                self.tasks.append(asyncio.create_task(self.stream(venue,kind,markets[i:i+100],i//100)))
                                await asyncio.sleep(1)
                await asyncio.sleep(900)

    async def stream(self,venue,kind,markets,shard):
        keys=[m.key for m in markets];lookup={m.symbol:m for m in markets};delay=1
        url=(f'wss://stream.bybit.com/v5/public/{"spot" if kind=="spot" else "linear"}' if venue=='bybit'
             else ('wss://api.gateio.ws/ws/v4/' if kind=='spot' else 'wss://fx-ws.gateio.ws/v4/ws/usdt'))
        connection=f'{venue}:{kind}:{shard}'
        while True:
            try:
                async with connect(url,ping_interval=None,max_queue=1024,open_timeout=45,close_timeout=5) as ws:
                    self.e.venue_status[venue].update(state='streaming',error=None)
                    sender=asyncio.create_task(self.subscribe(ws,venue,kind,markets))
                    heartbeat=asyncio.create_task(self.ping(ws,venue,kind))
                    sequences={}
                    try:
                        async for raw in self.messages(ws):
                            received=time.time();msg=json.loads(raw)
                            if not self.e.recorder.emit('ws',{'connection':connection,'message':msg},raw=True):
                                raise RuntimeError('recording queue full; coverage interrupted')
                            self.e.venue_status[venue]['last_message']=received
                            if msg.get('error') or msg.get('success') is False:raise RuntimeError(str(msg)[:250])
                            if venue=='bybit' and msg.get('topic','').startswith('orderbook.'):
                                d=msg['data'];m=lookup.get(d['s'])
                                if not m:continue
                                self.e.on_book(m.key,d['b'],d['a'],msg['type']=='snapshot' or d.get('u')==1,d.get('u',0),msg.get('ts',0),50)
                            elif venue=='gate' and msg.get('event')=='update':
                                d=msg.get('result',{})
                                if kind=='spot' and msg.get('channel')=='spot.order_book':
                                    m=lookup.get(d['s'])
                                    if m:self.e.on_book(m.key,d['bids'],d['asks'],True,d.get('lastUpdateId',0),d.get('t',0),20)
                                elif kind=='perp' and msg.get('channel')=='futures.obu':
                                    symbol=d.get('s','')
                                    # V2 uses s = ob.SYMBOL.400
                                    symbol=symbol.split('.')[1] if symbol.startswith('ob.') else symbol
                                    m=lookup.get(symbol)
                                    if not m:continue
                                    full=d.get('full',False);u=int(d.get('u',0));U=int(d.get('U',0))
                                    if not full and U!=sequences.get(symbol,-2)+1:raise RuntimeError('Gate sequence gap')
                                    sequences[symbol]=u
                                    self.e.on_book(m.key,d.get('b',[]),d.get('a',[]),full,u,d.get('t',0),400)
                            delay=1
                    finally:
                        sender.cancel();heartbeat.cancel();await asyncio.gather(sender,heartbeat,return_exceptions=True)
            except asyncio.CancelledError:
                self.e.invalidate(keys,'shutdown');raise
            except Exception as exc:
                self.reconnects+=1;self.e.venue_status[venue].update(state='reconnecting',error=str(exc)[:180],reconnects=self.reconnects)
                log.warning('%s: %s',connection,exc)
            finally:self.e.invalidate(keys,'connection_closed')
            await asyncio.sleep(delay+random.random());delay=min(60,delay*2)

    async def messages(self,ws):
        while True:
            yield await asyncio.wait_for(ws.recv(),timeout=45)

    async def subscribe(self,ws,venue,kind,markets):
        if venue=='bybit':
            for i in range(0,len(markets),10):
                await ws.send(json.dumps({'op':'subscribe','args':[f'orderbook.50.{m.symbol}' for m in markets[i:i+10]]}));await asyncio.sleep(.25)
        else:
            for m in markets:
                channel='spot.order_book' if kind=='spot' else 'futures.obu'
                payload=[m.symbol,'20','100ms'] if kind=='spot' else [f'ob.{m.symbol}.400']
                await ws.send(json.dumps({'time':int(time.time()),'channel':channel,'event':'subscribe','payload':payload}));await asyncio.sleep(.15)

    async def ping(self,ws,venue,kind):
        while True:
            await asyncio.sleep(15)
            msg={'op':'ping'} if venue=='bybit' else {'time':int(time.time()),'channel':f'{"spot" if kind=="spot" else "futures"}.ping'}
            await ws.send(json.dumps(msg))

    async def close(self):
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
