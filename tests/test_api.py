import json
from pathlib import Path
from fastapi.testclient import TestClient
import parallax.api as api

def test_local_api_and_validation(tmp_path,monkeypatch):
    monkeypatch.setenv('PARALLAX_OFFLINE','1');monkeypatch.setenv('PARALLAX_DATA',str(tmp_path/'data'))
    config=tmp_path/'settings.json';config.write_text(Path('config/settings.json').read_text());monkeypatch.setattr(api,'CONFIG',config)
    with TestClient(api.app) as client:
        assert client.get('/api/state').json()['summary']['routes']==0
        assert client.get('/api/detail',params={'route':'missing'}).status_code==404
        settings=json.loads(config.read_text())
        assert client.post('/api/assumptions',json=settings|{'trade_cad':-1}).status_code==422
        assert client.post('/api/assumptions',json=settings,headers={'Origin':'https://untrusted.example'}).status_code==403
        assert client.post('/api/assumptions',json=settings|{'trade_cad':25},headers={'Origin':'http://localhost:3000'}).status_code==200
        assert json.loads(config.read_text())['trade_cad']==25
        assert client.get('/api/history?hours=-1').status_code==422
        assert client.get('/api/catalog').json()['routes']==[]
