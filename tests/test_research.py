import copy,json,time
from decimal import Decimal as D
from pathlib import Path
import pytest
from parallax.models import Book,Market,common_step,economics,walk
from parallax.engine import Engine
from parallax.storage import Recorder

@pytest.fixture
def settings():return json.loads(Path('config/settings.json').read_text())

def market(venue,kind):return Market(venue,kind,'ABCUSDT','ABC',D('.1'),D('.1'),D('1'),D('.01'))

def book(bid,ask,q='1000'):
    b=Book();b.apply([[bid,q]],[[ask,q]]);return b

def test_depth_walking_and_insufficient_depth():
    assert walk([(D(1),D(2)),(D(2),D(3))],D(4))==D(6)
    assert walk([(D(1),D(2))],D(3)) is None

def test_common_step_is_not_just_maximum():
    assert common_step(D('.03'),D('.02'))==D('.06')

def test_fee_round_trip_and_monotonic_costs(settings):
    a,b=market('a','spot'),market('b','perp');x,y=book('.99','1'),book('1.02','1.03')
    s=settings|{'trade_cad':20,'cad_per_usdt':1,'spot_fee_bps':20,'perp_fee_bps':20,'holding_cost_bps':0,'execution_buffer_bps':0,'exit_gap_bps':0}
    v,reason=economics(a,b,x,y,s)
    assert reason is None and v['quantity']==20
    assert v['net']==pytest.approx(.2392) # .4 opening gap minus all four fees
    v2,_=economics(a,b,x,y,s|{'execution_buffer_bps':10})
    assert v2['net']<v['net']
    v3,_=economics(a,b,x,y,s|{'exit_gap_bps':20})
    assert v3['net']<v['net']

def test_contract_sizes_normalized():
    b=Book();b.apply([{'p':'1','s':10}],[{'p':'2','s':20}],multiplier=D('.001'))
    assert b.bids[D(1)]==D('.01')

def test_snapshot_delta_delete_and_reset():
    b=Book();b.apply([['1','2']],[['3','4']],sequence=10)
    b.apply([['1','0'],['2','5']],[],False,11)
    assert D(1) not in b.bids and b.bids[D(2)]==5
    assert not b.apply([['2','9']],[],False,10)
    b.apply([['.5','1']],[['1','2']],True,1)
    assert D(2) not in b.bids

def test_delta_without_snapshot_fails():
    with pytest.raises(ValueError):Book().apply([['1','2']],[['2','3']],False)

def setup_engine(tmp_path,settings):
    rec=Recorder(tmp_path);e=Engine(settings,rec)
    a,b=market('a','spot'),market('b','perp');e.catalog([a,b]);rid=next(iter(e.routes))
    e.books[a.key]=book('.99','1');e.books[b.key]=book('1.1','1.11')
    return e,rid

def test_episode_dedup_and_gap_censoring(tmp_path,settings):
    e,rid=setup_engine(tmp_path,settings)
    t=time.time();m=time.monotonic()
    e.evaluate(rid,t,m);episode=e.active[rid]['episode_id']
    e.evaluate(rid,t+1,m+1)
    assert e.active[rid]['episode_id']==episode
    e.evaluate(rid,t+20,m+20)
    assert not e.active
    assert e.history[0]['status']=='interrupted'
    assert e.history[0]['duration']==0 # cached quotes never extend observed intervals

def test_no_paper_for_unverified_identity(tmp_path,settings):
    e,rid=setup_engine(tmp_path,settings);e.evaluate(rid)
    assert not e.paper

def test_record_persistence(tmp_path):
    r=Recorder(tmp_path);r.start();r.emit('episode_end',{'episode_id':'e','duration':3},'r');r.close()
    records=Recorder(tmp_path).query(kind='episode_end')
    assert records[0]['duration']==3

def test_every_cross_venue_matching_route_discovered(tmp_path,settings):
    e=Engine(settings,Recorder(tmp_path))
    markets=[]
    for i in range(501):
        for venue in ('a','b'):
            for kind in ('spot','perp'):
                m=market(venue,kind);m.base=f'COIN{i}';m.symbol=f'COIN{i}USDT';markets.append(m)
    e.catalog(markets)
    assert len(e.routes)==1002
