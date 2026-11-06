"""Export recorded paper outcomes. Counts are observations, never daily forecasts."""
import argparse,collections,json,sqlite3,statistics
from pathlib import Path
from datetime import datetime,timezone

p=argparse.ArgumentParser();p.add_argument('--data',default='data/paper-v2');p.add_argument('--output',default='reports/paper-results.json');args=p.parse_args()
root=Path(args.data)
with sqlite3.connect((root/'research.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
    counts=dict(db.execute('SELECT kind,count(*) FROM events GROUP BY kind'))
    closes=[json.loads(x) for x, in db.execute("SELECT payload FROM events WHERE kind='paper_close' ORDER BY id")]
    coverage=[json.loads(x) for x, in db.execute("SELECT payload FROM events WHERE kind='coverage' ORDER BY id DESC LIMIT 1")]
# Deduplicate stable position ids so a repeated event cannot multiply profit.
closes=list({x['position_id']:x for x in closes}.values())
state=json.loads((root/'paper-state.json').read_text()) if (root/'paper-state.json').exists() else {}
result={'generated_at':datetime.now(timezone.utc).isoformat(),'source':str(root.resolve()),'event_counts':counts,
        'closed_trades_in_retained_events':len(closes),'wins':sum(x['realized_net_cad']>0 for x in closes),
        'losses':sum(x['realized_net_cad']<0 for x in closes),'net_cad_in_retained_events':sum(x['realized_net_cad'] for x in closes),
        'close_reasons':dict(collections.Counter(x['reason'] for x in closes)),
        'median_holding_seconds':statistics.median(x['holding_seconds'] for x in closes) if closes else None,
        'median_entry_latency_seconds':statistics.median(x['entry_latency_seconds'] for x in closes) if closes else None,
        'unresolved_positions':list(state.get('positions',{}).values()),
        'lifetime_realized_usdt':sum(state.get('realized',{}).values()),'latest_coverage':coverage[0] if coverage else None,
        'limitations':['Deterministic delayed-IOC stress simulation, not real fills or calibrated probability.',
                       'Retained SQLite events span at most 30 days; lifetime state totals can span longer.',
                       'Five-second whole-universe polling and bounded depth confirmation can miss brief windows.',
                       'Funding is a conservative time/current-rate allowance, not actual settlement history.',
                       'No profits are imputed to unresolved positions or missing observations.']}
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(out)
print(json.dumps({k:v for k,v in result.items() if k not in ('latest_coverage','unresolved_positions')},indent=2))
