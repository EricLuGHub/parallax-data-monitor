import json,time
from pathlib import Path
from decimal import Decimal as D
import pytest
from parallax.models import Market,Book,economics
from parallax.engine import Engine
from parallax.storage import Recorder
from parallax.paper import threshold,ioc
from parallax.identity import index_evidence
from parallax.network import MeteredClient,NetworkBudgetExceeded


def setup(tmp_path):
    s=json.loads(Path('config/settings.json').read_text())
    a=Market('gate','spot','ABC_USDT','ABC',D('.1'),D('.1'),D(1),D('.001'))
    b=Market('bybit','perp','ABCUSDT','ABC',D('.1'),D('.1'),D(1),D('.001'))
    rid=a.key+'|'+b.key
    s['identity_routes']={rid:{'expires_at':time.time()+3600,'method':'synthetic test evidence'}}
    e=Engine(s,Recorder(tmp_path));e.catalog([a,b]);return e,rid

def quotes(e,rid,t,spot=('.999','1'),perp=('1.03','1.031'),sizes=('1000','1000')):
    r=e.routes[rid]
    for key,prices,size in [(r['buy']['key'],spot,sizes[0]),(r['short']['key'],perp,sizes[1])]:
        book=Book();book.apply([[prices[0],size]],[[prices[1],size]])
        book.received=t; e.books[key]=book


def test_half_cent_is_cad_not_usdt():
    assert threshold({'min_net_cad':.005,'cad_per_usdt':1.38})==pytest.approx(.0036231884057971015)


def test_delayed_entry_exit_and_persistent_capital(tmp_path):
    e,rid=setup(tmp_path);t=time.time();quotes(e,rid,t);e.evaluate(rid,t)
    assert rid in e.pending and not e.paper
    e.evaluate(rid,t+1) # Old quotes cannot fill even after wall clock passes latency.
    assert not e.paper
    quotes(e,rid,t+2);e.evaluate(rid,t+2)
    assert e.paper[rid]['entry_latency_seconds']==2
    assert e.paper[rid]['status']=='open'
    # Real exit books converge; close is still delayed.
    quotes(e,rid,t+3,perp=('1','1.001'));e.evaluate(rid,t+3)
    assert 'close_due' in e.paper[rid]
    quotes(e,rid,t+4,perp=('1','1.001'));e.evaluate(rid,t+4)
    assert rid not in e.paper and e.paper_closed[0]['realized_net_cad']>.005
    assert sum(e.paper_realized.values())==pytest.approx(e.paper_closed[0]['realized_net'])
    assert sum(e.paper_reserved.values())==pytest.approx(0)
    restored=Engine(e.settings,Recorder(tmp_path))
    assert restored.trader.closed_count==1
    assert sum(restored.paper_realized.values())==pytest.approx(sum(e.paper_realized.values()))


def test_one_sided_fill_is_unwound_and_loss_counted(tmp_path):
    e,rid=setup(tmp_path);t=time.time();quotes(e,rid,t);e.evaluate(rid,t)
    quotes(e,rid,t+1,perp=('.9','.901'));e.evaluate(rid,t+1)
    assert e.paper[rid]['status']=='unwind_required'
    assert e.paper[rid]['short_quantity']==0
    quotes(e,rid,t+2,spot=('.98','.981'),perp=('.9','.901'));e.evaluate(rid,t+2)
    assert e.paper_closed[0]['reason']=='unmatched_entry'
    assert e.paper_closed[0]['realized_net']<0


def test_stale_books_never_close_and_restart_retains_exposure(tmp_path):
    e,rid=setup(tmp_path);t=time.time();quotes(e,rid,t);e.evaluate(rid,t)
    quotes(e,rid,t+1);e.evaluate(rid,t+1)
    e.books[e.routes[rid]['buy']['key']].valid=False
    e.evaluate(rid,t+4000)
    assert rid in e.paper and not e.paper_closed
    restored=Engine(e.settings,Recorder(tmp_path))
    assert rid in restored.paper and restored.paper[rid]['observation_gap']
    assert sum(restored.paper_reserved.values())>0


def test_partial_ioc_depth_haircut_and_tick_limit():
    q,c=ioc([(D(1),D(3)),(D('1.01'),D(100))],D(10),D(1),True,D('.1'),D('.5'))
    assert q==D('1.5') and c==D('1.5')


def test_index_evidence_rejects_ticker_collision_and_scaling(tmp_path):
    e,rid=setup(tmp_path);r=e.routes[rid];now=time.time()
    response={'retCode':0,'result':{'indexName':'ABCUSDT','updateTime':str(now*1000),'components':[{'exchange':'GateIO','spotPair':'ABC_USDT','multiplier':'1','weight':'.2'}]}}
    assert index_evidence(r,response,now)
    response['result']['components'][0]['spotPair']='OTHER_USDT'
    assert index_evidence(r,response,now) is None
    response['result']['components'][0].update(spotPair='ABC_USDT',multiplier='1000')
    assert index_evidence(r,response,now) is None


@pytest.mark.asyncio
async def test_network_budget_stops_further_requests():
    c=MeteredClient({'network_kib_per_second':1})
    try:
        with pytest.raises(NetworkBudgetExceeded):c.account(31*1024)
        with pytest.raises(NetworkBudgetExceeded):await c.get('https://unused.invalid')
        assert c.requests==0
    finally:await c.aclose()


def test_expired_pending_no_fill(tmp_path):
    e,rid=setup(tmp_path);t=time.time();quotes(e,rid,t);e.evaluate(rid,t)
    e.trader.expire(t+31)
    assert not e.pending and not e.paper and e.trader.rejected==1


def test_profit_target_can_be_lost_during_exit_delay(tmp_path):
    e,rid=setup(tmp_path);t=time.time();quotes(e,rid,t);e.evaluate(rid,t)
    quotes(e,rid,t+1);e.evaluate(rid,t+1)
    quotes(e,rid,t+2,perp=('1','1.001'));e.evaluate(rid,t+2)
    assert e.paper[rid]['close_reason']=='profit_target'
    quotes(e,rid,t+3,perp=('1.05','1.051'));e.evaluate(rid,t+3)
    assert e.paper_closed[0]['reason']=='profit_target'
    assert e.paper_closed[0]['realized_net']<0 # Trigger is not a guaranteed profitable fill.


def test_depth_shortfall_does_not_silently_shrink_50_dollar_trade(tmp_path):
    e,rid=setup(tmp_path);t=time.time();quotes(e,rid,t,sizes=('2','1000'))
    e.evaluate(rid,t)
    assert e.results[rid]['status']=='insufficient_depth' and not e.pending


@pytest.mark.asyncio
async def test_compressed_http_is_decoded_once_and_metered_on_wire():
    import gzip,httpx
    c=MeteredClient({'network_kib_per_second':256})
    await c.client.aclose()
    wire=gzip.compress(json.dumps({'rows':['data']*10000}).encode())
    async def handler(request):
        return httpx.Response(200,headers={'content-encoding':'gzip'},stream=httpx.ByteStream(wire))
    c.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        response=await c.get('https://unused.invalid')
        assert len(response.json()['rows'])==10000
        assert c.total==len(wire)
    finally:await c.aclose()


def test_unverified_positive_gap_is_not_a_verified_candidate(tmp_path):
    e,rid=setup(tmp_path);e.routes[rid].update(identity='symbol match — unverified',identity_evidence=None)
    t=time.time();quotes(e,rid,t);e.evaluate(rid,t)
    assert e.results[rid]['status']=='unverified_gap'
    assert e.summary()['verified_candidates']==0
    assert not e.pending
