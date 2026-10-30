import base64
import json
import httpx
import pytest
from fastapi import HTTPException
from ownit.github import GitHub
from ownit.llm import LLM
from ownit.models import Analysis, Evaluation, QuestionSet, Teaching
from ownit.main import create_app
from fastapi.testclient import TestClient


@pytest.mark.parametrize('pr,baseline,expected', [(None,None,None), (None,'old','old'), (7,'old','pr-base')])
def test_github_snapshots(pr, baseline, expected):
    requests = []
    def respond(request):
        path = request.url.path
        requests.append(path)
        if path == '/repos/acme/app':
            data = {'private':False, 'visibility':'public', 'default_branch':'main'}
        elif '/pulls/' in path:
            data = {'base':{'sha':'pr-base'}, 'head':{'sha':'pr-head'}}
        elif '/commits/' in path:
            data = {'sha':'head'}
        elif '/trees/' in path:
            data = {'truncated':False, 'tree':[
                {'path':'app.py','type':'blob','size':20,'sha':'blob'},
                {'path':'.env','type':'blob','size':10,'sha':'secret'},
                {'path':'huge.py','type':'blob','size':100000,'sha':'huge'}]}
        elif '/compare/' in path:
            data = {'files':[{'filename':'app.py','status':'modified','patch':'+print(1)'}, {'filename':'old.py','status':'removed','patch':'-old()'}]}
        elif '/blobs/blob' in path:
            data = {'encoding':'base64','size':9,'content':base64.b64encode(b'print(1)\n').decode()}
        else:
            raise AssertionError(path)
        return httpx.Response(200,json=data)
    gh = GitHub()
    gh.client.close()
    gh.client = httpx.Client(base_url='https://api.github.com', transport=httpx.MockTransport(respond))
    result = gh.fetch('acme/app', pr, None, baseline)
    gh.close()
    assert result['base_sha'] == expected
    assert result['sha'] == ('pr-head' if pr else 'head')
    assert list(result['files']) == ['app.py']
    assert not any('secret' in r or 'huge' in r for r in requests)
    if expected:
        assert 'old.py' in result['changed_files'] and 'removed old.py' in result['diff']


def test_private_rejected():
    gh = GitHub()
    gh.client.close()
    gh.client = httpx.Client(base_url='https://api.github.com', transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'private':True})))
    with pytest.raises(HTTPException) as err:
        gh.fetch('acme/private', None, None, None)
    assert err.value.status_code == 422
    gh.close()


def test_dartmouth_wire_format(monkeypatch):
    monkeypatch.setenv('DARTMOUTH_API_KEY','server-only-key')
    monkeypatch.setenv('DARTMOUTH_API_BASE_URL', 'https://chat.dartmouth.edu/api/')
    monkeypatch.setenv('DARTMOUTH_MODEL', 'account-model-id')
    payload = {'verdict':'uncertain', 'feedback':'Insufficient evidence.', 'knowledge_gap':'input assumptions', 'followup':None, 'evidence':[]}
    def post(url, **kwargs):
        assert url == 'https://chat.dartmouth.edu/api/chat/completions'
        assert kwargs['headers']['Authorization'] == 'Bearer server-only-key'
        body = kwargs['json']
        assert body['stream'] is False
        assert body['model'] == 'account-model-id'
        assert 'server-only-key' not in json.dumps(body)
        assert json.loads(body['messages'][1]['content'])['answer'].startswith('[REDACTED]')
        assert 'JSON Schema' in body['messages'][0]['content']
        assert 'response_format' not in body
        return httpx.Response(200, request=httpx.Request('POST', url), json={'choices':[{'message':{'content':json.dumps(payload)}}]})
    monkeypatch.setattr(httpx, 'post', post)
    ev = LLM().generate(Evaluation, 'grade', {'answer':'server-only-key token=untrusted-secret'})
    assert ev.verdict == 'uncertain'


@pytest.mark.parametrize('schema', [Analysis, Evaluation, QuestionSet, Teaching])
def test_strict_output_schemas(schema):
    def walk(node):
        if isinstance(node, dict):
            if node.get('type') == 'object':
                assert node['additionalProperties'] is False
                assert set(node['required']) == set(node['properties'])
            for value in node.values():
                walk(value)
        elif isinstance(node,list):
            for value in node:
                walk(value)
    walk(schema.model_json_schema())


def test_invalid_ai_response_is_actionable(monkeypatch):
    monkeypatch.setenv('DARTMOUTH_API_KEY', 'test-key')
    monkeypatch.setattr(httpx, 'post', lambda url, **kwargs: httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[]}))
    with pytest.raises(HTTPException) as err:
        LLM().generate(Evaluation,'grade',{})
    assert err.value.status_code == 502


@pytest.mark.parametrize('key', ['', 'PASTE_YOUR_DARTMOUTH_API_KEY_HERE', '   '])
def test_placeholder_is_not_a_configured_key(monkeypatch, tmp_path, key):
    monkeypatch.setenv('DARTMOUTH_API_KEY', key)
    client = TestClient(create_app(str(tmp_path/'placeholder.db')))
    assert client.get('/health').json()['live_ai_configured'] is False
    with pytest.raises(HTTPException) as err:
        LLM().generate(Evaluation, 'grade', {})
    assert err.value.status_code == 503


@pytest.mark.parametrize('content', ['not JSON', '{}'])
def test_dartmouth_output_is_validated(monkeypatch, content):
    monkeypatch.setenv('DARTMOUTH_API_KEY', 'test-key')
    monkeypatch.setattr(httpx, 'post', lambda url, **kwargs: httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':content}}]}))
    with pytest.raises(HTTPException) as err:
        LLM().generate(Evaluation, 'grade', {})
    assert err.value.status_code == 502


def test_completed_review_is_immutable(tmp_path):
    c = TestClient(create_app(str(tmp_path/'done.db')))
    r = c.post('/reviews',json={'demo':True}).json()
    path = f"/reviews/{r['id']}"
    r = c.post(path+'/questions').json()
    for q in r['questions']:
        result = c.post(path+'/answers',json={'question_id':q['id'], 'answer':'deny non-owner private access; set list linear; filter visibility authorization tags'})
        assert result.status_code == 200
    assert c.post(path+'/complete').status_code == 200
    assert c.post(path+'/teach',json={'concept':q['concept'],'message':'help'}).status_code == 409
    assert c.post(path+'/answers',json={'question_id':q['id'],'answer':'changed','challenge':True}).status_code == 409
