import asyncio,json,logging,os,time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field
from .engine import Engine
from .storage import Recorder
from .instance import InstanceLock
from .polling import Feeds

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
CONFIG=Path(os.environ.get('PARALLAX_CONFIG','config/settings.json'))

class Assumptions(BaseModel):
    trade_cad:float=Field(gt=0,le=100000)
    cad_per_usdt:float=Field(gt=.01,lt=100)
    spot_fee_bps:float=Field(ge=0,le=1000)
    perp_fee_bps:float=Field(ge=0,le=1000)
    execution_buffer_bps:float=Field(ge=0,le=1000)
    holding_cost_bps:float=Field(ge=0,le=1000)
    exit_gap_bps:float=Field(ge=-1000,le=1000)
    min_net_cad:float=Field(ge=0,le=1000)

@asynccontextmanager
async def lifespan(app):
    lock=InstanceLock(os.environ.get('PARALLAX_DATA','data/paper-v2'))
    try:
        async with running_app(app):
            yield
    finally:
        lock.close()

@asynccontextmanager
async def running_app(app):
    settings=json.loads(CONFIG.read_text())
    identities=CONFIG.parent/'identities.json'
    if identities.exists():settings['identity_routes']=json.loads(identities.read_text())
    recorder=Recorder(os.environ.get('PARALLAX_DATA','data/paper-v2'));recorder.start()
    engine=Engine(settings,recorder);feeds=Feeds(engine);app.state.engine=engine
    recorder.emit('assumptions',settings)
    tasks=[asyncio.create_task(engine.run())]
    if os.environ.get('PARALLAX_OFFLINE')!='1':tasks.append(asyncio.create_task(feeds.run()))
    try:yield
    finally:
        for rid in list(engine.active):engine.fail(rid,'invalid_book',time.time())
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True);await feeds.close()
        engine.trader.save()
        await asyncio.to_thread(recorder.close)

app=FastAPI(title='Parallax research — no trading endpoints',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],allow_methods=['GET','POST'],allow_headers=['Content-Type'])

@app.get('/api/state')
async def state(request:Request):return request.app.state.engine.snapshot()

@app.get('/api/stream')
async def stream(request:Request):
    async def events():
        while not await request.is_disconnected():
            yield 'data: '+json.dumps(request.app.state.engine.snapshot(),allow_nan=False)+'\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.get('/api/detail')
async def detail(request:Request,route:str):
    e=request.app.state.engine
    if route not in e.routes:raise HTTPException(404,'Unknown route')
    r=e.routes[route];books={}
    for side in ('buy','short'):
        b=e.books[r[side]['key']]
        books[side]={'bids':[[float(p),float(q)] for p,q in b.levels('bids')[:20]],
                     'asks':[[float(p),float(q)] for p,q in b.levels('asks')[:20]],'received':b.received,'valid':b.valid}
    events=await asyncio.to_thread(e.recorder.query,route=route,limit=100)
    return {'route':e.results.get(route,r),'books':books,'timeline':list(e.timeline[route]),'events':events}

@app.get('/api/history')
async def history(request:Request,hours:float=Query(24,gt=0,le=720),limit:int=Query(1000,ge=1,le=10000)):
    return await asyncio.to_thread(request.app.state.engine.recorder.query,kind='episode_end',limit=limit,since=time.time()-hours*3600)

@app.get('/api/catalog')
async def catalog(request:Request):
    e=request.app.state.engine
    return {'markets':[m.public() for m in e.markets.values()],'routes':list(e.routes.values()),'excluded':e.excluded}

@app.post('/api/assumptions')
async def assumptions(request:Request,values:Assumptions):
    origin=request.headers.get('origin')
    if origin and origin not in ('http://localhost:3000','http://127.0.0.1:3000'):raise HTTPException(403,'Local dashboard only')
    e=request.app.state.engine
    for rid in list(e.active):e.fail(rid,'assumptions_changed',time.time())
    for rid in list(e.pending):e.trader.reject(rid,'assumptions_changed')
    e.settings.update(values.model_dump());e.dirty.update(e.routes)
    e.recorder.emit('assumptions',e.settings)
    # Research assumptions only. Existing paper positions retain entry-time assumptions.
    temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps({k:v for k,v in e.settings.items() if k!='identity_routes'},indent=2)+'\n');temp.replace(CONFIG)
    return e.settings
