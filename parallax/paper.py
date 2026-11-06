"""Deterministic delayed IOC stress simulation. No orders and no calibrated fill odds."""
import copy,json,math,time,uuid
from decimal import Decimal as D,ROUND_DOWN
from .models import walk,common_step,economics


def threshold(settings):
    return settings['min_net_cad']/settings['cad_per_usdt'] if 'min_net_cad' in settings else settings['min_net_usdt']


def ioc(levels,quantity,limit,buy,step,haircut):
    available=[]
    for price,size in levels:
        if (buy and price>limit) or (not buy and price<limit):break
        available.append((price,size*haircut))
    fill=min(quantity,sum((q for _,q in available),D(0)))
    fill=(fill/step).to_integral_value(rounding=ROUND_DOWN)*step
    return fill,walk(available,fill) if fill else D(0)


class PaperTrader:
    def __init__(self,engine):
        self.e=engine;self.path=engine.recorder.root/'paper-state.json';self.closed_count=0;self.rejected=0;self.last_error=None
        if self.path.exists():
            saved=json.loads(self.path.read_text())
            self.e.paper.update(saved['positions']);self.e.paper_reserved.update(saved['reserved']);self.e.paper_realized.update(saved['realized'])
            self.e.paper_closed.extend(saved.get('closed',[]));self.closed_count=saved.get('closed_count',0);self.rejected=saved.get('rejected',0)
            for p in self.e.paper.values():p['observation_gap']=True;p['close_status']='awaiting fresh books after restart'
        # Pending orders have never filled; do not revive them after downtime.

    def save(self):
        payload={'positions':self.e.paper,'reserved':dict(self.e.paper_reserved),'realized':dict(self.e.paper_realized),
                 'closed':list(self.e.paper_closed),'closed_count':self.closed_count,'rejected':self.rejected}
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(payload,indent=2)+'\n');temp.replace(self.path)

    def schedule(self,rid,row,now):
        e=self.e
        if not e.settings.get('paper_enabled',True) or len(e.paper)+len(e.pending)>=e.settings.get('paper_max_open',5):return
        if e.recorder.error or e.recorder.dropped:return
        a=e.markets[row['buy']['key']];b=e.markets[row['short']['key']]
        ticks=e.settings.get('paper_limit_ticks',1)
        q=D(str(row['quantity']))
        # Limits are executable VWAP rounded out to a valid price tick, plus the chosen cushion.
        buy_limit=(D(str(row['buy_vwap']))/a.tick).to_integral_value(rounding='ROUND_CEILING')*a.tick+ticks*a.tick
        short_limit=(D(str(row['short_vwap']))/b.tick).to_integral_value(rounding=ROUND_DOWN)*b.tick-ticks*b.tick
        if short_limit<=0:return
        e.pending[rid]={'due':now+e.settings.get('paper_latency_ms',500)/1000,'created':now,'quantity':str(q),
            'buy_limit':str(buy_limit),'short_limit':str(short_limit),'assumptions':copy.deepcopy(e.settings),
            'episode_id':row['episode']['episode_id'] if row.get('episode') else None}
        e.recorder.emit('paper_signal',{'id':rid,**e.pending[rid]},rid)

    def reject(self,rid,reason):
        self.e.pending.pop(rid,None);self.rejected+=1
        self.e.recorder.emit('paper_reject',{'id':rid,'reason':reason},rid);self.save()

    def expire(self,now):
        for rid,p in list(self.e.pending.items()):
            if now-p['created']>self.e.settings.get('paper_entry_expiry_seconds',30):self.reject(rid,'confirmation_expired')
        for p in self.e.paper.values():
            p['holding_seconds']=now-p['opened_at']
            if now-p.get('close_observed_at',0)>self.e.settings['stale_seconds']:
                p['close_status']='awaiting fresh depth; last estimate stale'

    def fresh(self,rid,now):
        e=self.e
        if rid not in e.routes:return False
        r=e.routes[rid];a=e.books[r['buy']['key']];b=e.books[r['short']['key']]
        return a.valid and b.valid and max(time.monotonic()-a.mono,time.monotonic()-b.mono)<=e.settings['stale_seconds'] and abs(a.received-b.received)<=e.settings['max_skew_seconds']

    def tick(self,rid,now):
        e=self.e
        if not self.fresh(rid,now):return
        r=e.routes[rid];a=e.markets[r['buy']['key']];b=e.markets[r['short']['key']]
        ab=e.books[a.key];bb=e.books[b.key]
        if rid in e.pending and rid not in e.paper:
            p=e.pending[rid];s=p['assumptions']
            if min(ab.received,bb.received)<p['due']:return
            if r['identity']!='reviewed':return self.reject(rid,'identity_no_longer_reviewed')
            # Once an IOC is scheduled, do not cherry-pick by rechecking profitability at fill time.
            qty=D(p['quantity']);haircut=D(str(s.get('paper_depth_fraction',.5)))
            lq,lc=ioc(ab.levels('asks'),qty,D(p['buy_limit']),True,a.step,haircut)
            sq,sc=ioc(bb.levels('bids'),qty,D(p['short_limit']),False,b.step,haircut)
            if not lq and not sq:return self.reject(rid,'both_ioc_unfilled')
            capital=s['paper_capital_cad']/s['cad_per_usdt']/2
            rb=float(lc)*(1+s['spot_fee_bps']/10000);rs=2*float(sc)
            if e.paper_reserved[a.venue]+rb>capital+e.paper_realized[a.venue] or e.paper_reserved[b.venue]+rs>capital+e.paper_realized[b.venue]:return self.reject(rid,'insufficient_simulated_collateral')
            e.pending.pop(rid)
            e.paper_reserved[a.venue]+=rb;e.paper_reserved[b.venue]+=rs
            pos={'id':rid,'position_id':uuid.uuid4().hex,'base':r['base'],'route':copy.deepcopy(r),'opened_at':now,
                'long_quantity':float(lq),'short_quantity':float(sq),'quantity':float(min(lq,sq)),
                'requested_quantity':float(qty),'entry_cost':float(lc),'entry_proceeds':float(sc),
                'entry_fees':float(lc)*s['spot_fee_bps']/10000+float(sc)*s['perp_fee_bps']/10000,
                'reserves':{a.venue:rb,b.venue:rs},'assumptions':s,'status':'open' if lq==sq else 'unwind_required',
                'model':'delayed independent IOC; 50% displayed depth by default; deterministic stress, not fill probability',
                'entry_latency_seconds':now-p['created'],'entry_fill_fraction':float(min(lq,sq)/qty),
                'identity_evidence':r.get('identity_evidence'),'episode_id':p.get('episode_id')}
            if lq!=sq:pos.update(close_due=now+s.get('paper_latency_ms',500)/1000,close_reason='unmatched_entry')
            e.paper[rid]=pos;e.recorder.emit('paper_open',pos,rid);self.save()
        if rid not in e.paper:return
        p=e.paper[rid];s=p['assumptions'];lq=D(str(p['long_quantity']));sq=D(str(p['short_quantity']))
        haircut=D(str(s.get('paper_depth_fraction',.5)))
        sell=walk([(x,y*haircut) for x,y in ab.levels('bids')],lq) if lq else D(0)
        cover=walk([(x,y*haircut) for x,y in bb.levels('asks')],sq) if sq else D(0)
        if sell is None or cover is None:
            p['close_status']='insufficient depth; exposure retained';return
        elapsed=now-p['opened_at']
        funding=e.funding.get(b.key,{})
        interval=funding.get('interval_hours') or b.funding_interval_hours or 8
        rate=float(funding.get('rate') or 0)
        # Never credit favorable funding. Flat allowance grows for long holds; adverse rate stress is separate.
        hold_base=max(p['entry_cost'],p['entry_proceeds'])
        allowance=hold_base*s['holding_cost_bps']/10000*max(1,elapsed/(8*3600))
        adverse=hold_base*max(0,-rate)*math.ceil(max(elapsed,0)/(interval*3600))
        holding=max(allowance,adverse,p.get('holding_allowance',0))
        buffer=max(p['entry_cost'],p['entry_proceeds'])*s['execution_buffer_bps']/10000
        fees=float(sell)*s['spot_fee_bps']/10000+float(cover)*s['perp_fee_bps']/10000
        pnl=float(sell-cover)+p['entry_proceeds']-p['entry_cost']-p['entry_fees']-fees-holding-buffer
        p.update(close_estimate=pnl,close_estimate_cad=pnl*s['cad_per_usdt'],holding_seconds=elapsed,close_observed_at=now,
                 close_status='fresh depth stress estimate',holding_allowance=holding,execution_buffer=buffer,exit_fees=fees,
                 funding_rate_observed=rate,funding_model='max(time-scaled allowance, adverse current-rate scenario); not settlement accrual')
        reason='profit_target' if pnl>=threshold(s) else 'stop_loss' if pnl*s['cad_per_usdt']<=-s.get('paper_stop_loss_cad',2) else 'timeout' if elapsed>=s['paper_timeout_seconds'] else None
        if 'close_due' not in p and reason:
            p.update(close_due=now+s.get('paper_latency_ms',500)/1000,close_reason=reason)
            self.save();return
        if 'close_due' not in p or min(ab.received,bb.received)<p['close_due']:return
        # Execute on the next fresh post-delay books even if the target disappeared: no hindsight cancellation.
        p.update(closed_at=now,status='closed',reason=p['close_reason'],realized_net=pnl,realized_net_cad=pnl*s['cad_per_usdt'],exit_spot_proceeds=float(sell),exit_short_cost=float(cover))
        for venue,reserve in p['reserves'].items():e.paper_reserved[venue]-=reserve
        e.paper_realized[a.venue]+=float(sell)-p['entry_cost']-(float(sell)+p['entry_cost'])*s['spot_fee_bps']/10000-buffer/2
        e.paper_realized[b.venue]+=p['entry_proceeds']-float(cover)-(float(cover)+p['entry_proceeds'])*s['perp_fee_bps']/10000-holding-buffer/2
        e.paper_closed.appendleft(p);e.paper.pop(rid);self.closed_count+=1
        e.recorder.emit('paper_close',p,rid);self.save()
