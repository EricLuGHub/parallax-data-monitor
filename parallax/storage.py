"""One background writer. Raw frames and persistent research events, never secrets."""
import copy,gzip,json,logging,queue,sqlite3,threading,time,uuid
from pathlib import Path

class Recorder:
    def __init__(self,root='data',max_queue=50000):
        self.root=Path(root); self.root.mkdir(exist_ok=True,parents=True)
        self.db_path=self.root/'research.sqlite3'
        self.run_id=uuid.uuid4().hex
        self.q=queue.Queue(maxsize=max_queue); self.dropped=0; self.error=None; self.written=0
        self.stop=threading.Event(); self.thread=None; self.last_error=None
        with sqlite3.connect(self.db_path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts REAL, kind TEXT, route TEXT, payload TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS events_kind_ts ON events(kind,ts)')
            db.execute('CREATE INDEX IF NOT EXISTS events_route_ts ON events(route,ts)')

    def start(self):
        self.thread=threading.Thread(target=self._writer,daemon=True);self.thread.start()
        self.emit('run_start',{'run_id':self.run_id})

    def emit(self,kind,payload,route='',raw=False):
        try:
            self.q.put_nowait((time.time(),kind,route,payload if raw else copy.deepcopy(payload),raw));return True
        except queue.Full:
            self.dropped+=1;return False

    def _writer(self):
        db=sqlite3.connect(self.db_path);db.execute('PRAGMA journal_mode=WAL')
        handle=None;bucket=None;last_prune=0
        try:
            while not self.stop.is_set() or not self.q.empty():
                batch=[]
                try: batch.append(self.q.get(timeout=.5))
                except queue.Empty: continue
                while len(batch)<1000:
                    try:batch.append(self.q.get_nowait())
                    except queue.Empty:break
                try:
                    for ts,kind,route,payload,raw in batch:
                        encoded=json.dumps(payload,separators=(',',':'),default=str)
                        if raw:
                            key=time.strftime('%Y%m%d-%H%M',time.gmtime(ts))
                            if bucket!=key:
                                if handle:handle.close()
                                handle=gzip.open(self.root/f'frames-{key}-{self.run_id[:8]}.jsonl.gz','at');bucket=key
                            handle.write(json.dumps({'ts':ts,'kind':kind,'route':route,'data':payload},separators=(',',':'),default=str)+'\n')
                        else:db.execute('INSERT INTO events(ts,kind,route,payload) VALUES(?,?,?,?)',(ts,kind,route,encoded))
                    db.commit()
                    if handle:handle.flush()
                    self.written+=len(batch);self.error=None
                    if time.time()-last_prune>60:
                        files=sorted(self.root.glob('frames-*.jsonl.gz'));total=sum(f.stat().st_size for f in files)
                        for f in files:
                            if bucket and bucket in f.name:continue
                            if f.stat().st_mtime<time.time()-86400 or total>2*1024**3:
                                size=f.stat().st_size; f.unlink();total-=size
                        db.execute('DELETE FROM events WHERE ts < ?', (time.time()-30*86400,));db.commit()
                        last_prune=time.time()
                except Exception as e:
                    self.error=str(e);self.last_error=str(e);self.dropped+=len(batch)
                    logging.exception("Recorder batch lost")
        finally:
            if handle:handle.close()
            db.close()

    def query(self,kind=None,route=None,limit=1000,since=0):
        where=['ts>=?'];args=[since]
        if kind:where.append('kind=?');args.append(kind)
        if route:where.append('route=?');args.append(route)
        with sqlite3.connect(self.db_path,timeout=5) as db:
            rows=db.execute('SELECT ts,kind,route,payload FROM events WHERE '+' AND '.join(where)+' ORDER BY id DESC LIMIT ?',args+[limit]).fetchall()
        return [{'ts':ts,'kind':k,'route':r,**json.loads(p)} for ts,k,r,p in rows]

    def close(self):
        self.emit('run_end',{'run_id':self.run_id});self.stop.set()
        if self.thread:self.thread.join(timeout=10)
