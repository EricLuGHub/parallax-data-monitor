import asyncio,copy,json,time,uuid
from collections import Counter,defaultdict,deque
from decimal import Decimal as D
from .models import Book,economics,walk
from .paper import PaperTrader,threshold

class Engine:
    def __init__(self,settings,recorder):
        self.settings=settings;self.recorder=recorder;self.markets={};self.books={};self.routes={};self.by_market=defaultdict(set)
        self.results={};self.active={};self.history=deque(maxlen=2000);self.timeline=defaultdict(lambda:deque(maxlen=300))
        self.venue_status={};self.excluded=[];self.started=time.time();self.messages=0;self.dirty=set()
        self.paper={};self.paper_closed=deque(maxlen=1000);self.paper_reserved=defaultdict(float)
        self.seen_valid=set();self.previous_state={};self.last_timeline={};self.evaluations=0
        self.paper_realized=defaultdict(float);self.recording_lost=0;self.loop_lag=0;self.discovery_version=0
        self.pending={};self.funding={};self.network=None;self.screening={}
        self.trader=PaperTrader(self)

    def catalog(self,markets):
        self.markets.update({m.key:m for m in markets})
        for m in markets:self.books.setdefault(m.key,Book())
        old_routes=self.routes
        self.routes={};self.by_market=defaultdict(set)
        spots=[m for m in self.markets.values() if m.kind=='spot']
        shorts=defaultdict(list)
        for m in self.markets.values():
            if m.kind=='perp':shorts[m.base].append(m)
        overrides=self.settings.get('identity_routes',{})
        for a in spots:
            for b in shorts[a.base]:
                if a.venue==b.venue:continue
                key=f'{a.key}|{b.key}'
                identity=overrides.get(key)
                if identity and identity.get('expires_at',0)<time.time():identity=None
                route={'id':key,'base':a.base,'buy':a.public(),'short':b.public(),
                    'identity':'reviewed' if identity else 'symbol match — unverified',
                    'identity_evidence':identity,'eligibility':'not checked'}
                self.routes[key]=route
                self.by_market[a.key].add(key);self.by_market[b.key].add(key)
        for rid in set(old_routes)-set(self.routes):
            if rid in self.active:
                ep=self.active.pop(rid);ep.update(ended_at=time.time(),reason='market_removed',status='interrupted',duration=max(0,ep['last_seen']-ep['started_at']))
                self.history.appendleft(ep);self.recorder.emit('episode_end',ep,rid)
            if rid in self.pending:self.trader.reject(rid,'market_removed')
            if rid in self.paper:self.paper[rid]['close_status']='market removed; unresolved exposure retained'
        self.results={k:v for k,v in self.results.items() if k in self.routes}
        self.dirty.update(self.routes);self.discovery_version+=1
        self.recorder.emit('catalog',{'markets':[m.public() for m in self.markets.values()], 'routes':list(self.routes.values()),'excluded':self.excluded})

    def invalidate(self,keys,reason):
        for key in keys:
            if key in self.books:self.books[key].valid=False
            self.dirty.update(self.by_market[key])
        self.recorder.emit('feed_gap',{'keys':keys,'reason':reason})

    def on_book(self,key,bids,asks,snapshot,sequence,exchange_ms,max_depth):
        market=self.markets[key]
        if self.books[key].apply(bids,asks,snapshot,sequence,exchange_ms,market.multiplier,max_depth):
            self.messages+=1;self.dirty.update(self.by_market[key])

    def fail(self,rid,reason,now):
        self.results[rid]={'id':rid,'status':reason,**self.routes[rid]}
        self.previous_state[rid]=reason
        if rid in self.active:
            ep=self.active.pop(rid);ep.update(ended_at=now,reason=reason,status='interrupted' if reason in ('stale_feed','observation_skew','invalid_book','sleep_gap') else 'ended')
            ep['duration']=max(0,ep['last_seen']-ep['started_at']);self.history.appendleft(ep)
            self.recorder.emit('episode_end',ep,rid)

    def evaluate(self,rid,now=None,mono=None):
        now=now or time.time();mono=mono or time.monotonic();r=self.routes[rid]
        if r.get('identity_evidence') and r['identity_evidence'].get('expires_at',0)<now:
            r.update(identity='symbol match — unverified',identity_evidence=None)
        self.trader.tick(rid,now)
        a=self.markets[r['buy']['key']];b=self.markets[r['short']['key']];ab=self.books[a.key];bb=self.books[b.key]
        if not ab.valid or not bb.valid:return self.fail(rid,'invalid_book',now)
        if max(mono-ab.mono,mono-bb.mono)>self.settings['stale_seconds']:return self.fail(rid,'stale_feed',now)
        if abs(ab.received-bb.received)>self.settings['max_skew_seconds']:return self.fail(rid,'observation_skew',now)
        value,reason=economics(a,b,ab,bb,self.settings)
        if reason:return self.fail(rid,reason,now)
        observed=min(ab.received,bb.received)
        prev=self.previous_state.get(rid)
        row={**r,**value,'observed_at':now,'buy_received':ab.received,'short_received':bb.received,
            'status':('candidate' if r['identity']=='reviewed' else 'unverified_gap') if value['net']>=threshold(self.settings) else 'below_threshold',
            'qualification':'conditional scenario; not an executable claim','net_cad':value['net']*self.settings['cad_per_usdt']}
        self.results[rid]=row;self.evaluations+=1
        if now-self.last_timeline.get(rid,0)>=2:
            self.last_timeline[rid]=now
            self.timeline[rid].append({'ts':now,'net':value['net'],'gap':value['entry_gap_bps']})
        if row['status'] in ('candidate','unverified_gap'):
            if rid not in self.active:
                ep={'episode_id':uuid.uuid4().hex,'id':rid,'base':r['base'],'started_at':observed,'last_seen':observed,
                    'peak_net':value['net'],'net':value['net'],'status':'active','left_censored':prev not in ('below_threshold',),
                    'run_id':self.recorder.run_id}
                self.active[rid]=ep;self.recorder.emit('episode_start',{**ep,'snapshot':row,'assumptions':self.settings},rid)
            ep=self.active[rid];ep.update(last_seen=max(ep['last_seen'],observed),net=value['net'],peak_net=max(ep['peak_net'],value['net']))
            row['episode']=dict(ep,duration=max(0,ep['last_seen']-ep['started_at']))
            # Only reviewed asset identities are admitted into automatic paper positions.
            if rid not in self.paper and rid not in self.pending and r['identity']=='reviewed' and not ep.get('paper_attempted'):
                ep['paper_attempted']=True;self.trader.schedule(rid,row,now)
        elif rid in self.active:
            self.fail(rid,'below_threshold',now);self.results[rid]=row
        self.previous_state[rid]=row['status'];self.seen_valid.add(rid)

    async def run(self):
        last=time.monotonic();last_checkpoint=0
        while True:
            await asyncio.sleep(.1)
            mono=time.monotonic();now=time.time();self.loop_lag=max(0,mono-last-.1)
            if mono-last>5:
                self.invalidate(list(self.books),'sleep_or_processing_gap')
            last=mono
            dirty=self.dirty;self.dirty=set()
            # Also reevaluate existing episodes/positions; their timers must stop on stale data.
            self.trader.expire(now)
            dirty.update(self.active);dirty.update(self.paper);dirty.update(self.pending)
            # Age stale negative routes too, so coverage cannot silently retain old values.
            dirty.update(k for k,v in self.results.items() if now-v.get('observed_at',now)>self.settings['stale_seconds'])
            for rid in dirty:
                if rid in self.routes:self.evaluate(rid,now,mono)
            if now-last_checkpoint>=5:
                last_checkpoint=now
                for rid,ep in self.active.items():self.recorder.emit('episode_checkpoint',ep,rid)
                self.recorder.emit('coverage',self.summary())
                for rid,p in self.paper.items():self.recorder.emit('paper_checkpoint',p,rid)

    def summary(self):
        counts=Counter(x.get('status') for x in self.results.values())
        return {'at':time.time(),'started':self.started,'run_id':self.recorder.run_id,'markets':len(self.markets),
            'coins':len({r['base'] for r in self.routes.values()}),'routes':len(self.routes),
            'valid_routes':counts['candidate']+counts['unverified_gap']+counts['below_threshold'],'active':len(self.active),'messages':self.messages,
            'reviewed_routes':sum(r['identity']=='reviewed' for r in self.routes.values()),
            'verified_candidates':sum(v.get('status')=='candidate' and v.get('identity')=='reviewed' for v in self.results.values()),
            'screening':self.screening,'network':self.network.summary() if self.network else None,
            'paper_summary':{'open':len(self.paper),'pending':len(self.pending),'closed':self.trader.closed_count,'rejected':self.trader.rejected,
                'realized_usdt':sum(self.paper_realized.values()),'reserved_usdt':dict(self.paper_reserved)},
            'evaluations':self.evaluations,'status_counts':dict(counts),'venues':self.venue_status,'excluded_count':len(self.excluded),
            'recording':{'written':self.recorder.written,'queue':self.recorder.q.qsize(),'dropped':self.recorder.dropped,'error':self.recorder.error,'last_error':self.recorder.last_error},
            'loop_lag_ms':round(self.loop_lag*1000,2),'settings':{k:v for k,v in self.settings.items() if k!='identity_routes'},'discovery_version':self.discovery_version}

    def snapshot(self):
        rows=sorted(self.results.values(),key=lambda x:x.get('net',float('-inf')),reverse=True)
        return {'summary':self.summary(),'routes':rows,'episodes':list(self.history),
            'pending':list(self.pending.values()),'paper':list(self.paper.values()),'paper_closed':list(self.paper_closed)}
