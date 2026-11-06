"""Conservative directional research evidence from the perpetual issuer's index."""
from decimal import Decimal as D

def index_evidence(route,response,now):
    if route['buy']['venue']!='gate' or route['short']['venue']!='bybit':return None
    if response.get('retCode')!=0:return None
    result=response.get('result',{})
    if result.get('indexName')!=route['short']['symbol']:return None
    if abs(now-float(result.get('updateTime',0))/1000)>60:return None
    for component in result.get('components',[]):
        if component.get('exchange') not in ('GateIO','Gate','Gate.io'):continue
        if component.get('spotPair')!=route['buy']['symbol']:continue
        if D(component.get('multiplier','0'))!=1 or D(component.get('weight','0'))<=0:continue
        return {'method':'issuer index links exact Gate spot pair, multiplier 1',
                'source':'https://api.bybit.com/v5/market/index-price-components?indexName='+result['indexName'],
                'checked_at':now,'expires_at':now+3600,'component':component,
                'scope':'directional paper research evidence; not deposit-chain or account eligibility verification'}
    return None
