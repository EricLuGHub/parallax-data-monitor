"""Read-only episode audit. No exchange calls and no inferred trading profits."""
import argparse, collections, json, sqlite3, statistics
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

parser=argparse.ArgumentParser()
parser.add_argument('--database',default='data/research.sqlite3')
parser.add_argument('--output',default='reports/recording-audit.json')
args=parser.parse_args()
with sqlite3.connect(Path(args.database).resolve().as_uri()+'?mode=ro',uri=True) as db:
    rows=[{'ts':t,'kind':k,'payload':json.loads(p)} for t,k,p in db.execute('SELECT ts,kind,payload FROM events ORDER BY ts')]
by=collections.defaultdict(list)
for r in rows: by[r['kind']].append(r)
ends=list({r['payload']['episode_id']:r['payload'] for r in by['episode_end']}.values())
starts={r['payload']['episode_id']:r['payload'] for r in by['episode_start']}
def stats(xs):
    return {'count':len(xs),'median_seconds':statistics.median(xs) if xs else None,'max_seconds':max(xs,default=None)}
groups=collections.defaultdict(list)
for e in ends: groups[e['base']].append(e)
report={
 'database':str(Path(args.database).resolve()),
 'start_local':datetime.fromtimestamp(rows[0]['ts'],ZoneInfo('America/Toronto')).isoformat(),
 'end_local':datetime.fromtimestamp(rows[-1]['ts'],ZoneInfo('America/Toronto')).isoformat(),
 'elapsed_minutes':(rows[-1]['ts']-rows[0]['ts'])/60,
 'event_counts':{k:len(v) for k,v in by.items()},
 'end_reasons':dict(collections.Counter(e['reason'] for e in ends)),
 'all_episode_durations':stats([e['duration'] for e in ends]),
 'threshold_end_durations':stats([e['duration'] for e in ends if e['reason']=='below_threshold']),
 'latest_coverage':by['coverage'][-1]['payload'],
 'assets':[]}
for base,es in sorted(groups.items(),key=lambda x:-len(x[1])):
    first=[starts[e['episode_id']]['snapshot'] for e in es if e['episode_id'] in starts]
    report['assets'].append({'base':base,'episodes':len(es),
      'reasons':dict(collections.Counter(e['reason'] for e in es)),
      'duration':stats([e['duration'] for e in es]),
      'first_net_usdt_median':statistics.median(s['net'] for s in first) if first else None,
      'entry_gap_bps_median':statistics.median(s['entry_gap_bps'] for s in first) if first else None})
report['limitations']=['Ticker identity unverified; zero verified round trips.',
 'Overlapping runs are included; episode IDs are deduplicated but economic opportunities are not.',
 'Interrupted duration is a censored observation, not a spread lifetime.',
 'First-observation economics assume future convergence; neither peaks nor episode counts are earnings.']
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
print(out)
print(json.dumps({k:v for k,v in report.items() if k not in ('assets','latest_coverage')},indent=2))
