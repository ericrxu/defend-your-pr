import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from pydantic import ValidationError
from ownit.main import create_app
from ownit.models import Analysis, Evaluation, Evidence, QuestionSet, Teaching, CreateReview
from ownit.github import parse_url, GitHub
from ownit import demo
from ownit.db import Store
from ownit.security import redact, safe_path


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / 'reviews.db')))


def create(client, version='initial'):
    r = client.post('/reviews', json={'demo': True, 'demo_version': version})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize('url,expected', [
    ('https://github.com/acme/code', ('acme/code', None)),
    ('https://github.com/acme/code.git/', ('acme/code', None)),
    ('https://github.com/acme/code/pull/42', ('acme/code', 42)),
])
def test_url(url, expected):
    assert parse_url(url) == expected


@pytest.mark.parametrize('url', ['http://github.com/a/b', 'https://github.com.evil.com/a/b', 'https://github.com/a/b?secret=x', 'https://github.com/a/b/pull/0', 'https://github.com/a/b/tree/main', 'https://user:pass@github.com/a/b', 'https://github.com/../x', 'file:///etc/passwd'])
def test_reject_url(url):
    with pytest.raises(HTTPException):
        parse_url(url)


def test_analysis_schema():
    a = demo.analysis(demo.snapshot('initial', None))
    assert Analysis.model_validate_json(a.model_dump_json()) == a
    with pytest.raises(ValidationError):
        Evidence(path='x', start=8, end=2)
    with pytest.raises(ValidationError):
        Analysis.model_validate({'review_type': 'other'})
    with pytest.raises(ValidationError):
        QuestionSet(questions=[])


def test_initial_change_and_completed_baseline(client):
    first = create(client)
    assert first['analysis']['review_type'] == 'initial'
    assert create(client, 'modified')['analysis']['review_type'] == 'initial'
    assert client.post(f"/reviews/{first['id']}/complete").status_code == 409
    r = client.post(f"/reviews/{first['id']}/questions").json()
    for q in r['questions']:
        response = client.post(f"/reviews/{r['id']}/answers", json={'question_id': q['id'], 'answer': 'owner private deny set list linear filter authorization tags'})
        assert response.status_code == 200
    assert client.post(f"/reviews/{r['id']}/complete").status_code == 200
    change = create(client, 'modified')
    assert change['analysis']['review_type'] == 'change'
    assert change['base_sha'] == 'demo-v1'
    assert set(change['analysis']['changed_files']) == {'auth.py', 'search.py'}
    assert '+    seen = set()' in change['diff']


def test_test_teach_retest_and_persistence(client):
    r = create(client)
    id = r['id']
    qs = client.post(f'/reviews/{id}/questions').json()['questions']
    assert 3 <= len(qs) <= 7
    assert all('rubric' not in q for q in qs)
    assert client.post(f'/reviews/{id}/questions').json()['questions'] == qs
    q = qs[0]
    assert client.post(f'/reviews/{id}/retest', json={'question_id': q['id']}).status_code == 409
    r = client.post(f'/reviews/{id}/answers', json={'question_id': q['id'], 'answer': 'It always works.'}).json()
    ev = Evaluation.model_validate(r['answers'][0]['evaluation'])
    assert ev.verdict == 'incorrect'
    assert ev.knowledge_gap
    assert client.post(f'/reviews/{id}/answers', json={'question_id': q['id'], 'answer':'duplicate'}).status_code == 409
    r = client.post(f'/reviews/{id}/teach', json={'concept': q['concept'], 'question_id': q['id'], 'message': 'Help me trace a private document.'}).json()
    assert r['status'] == 'teaching'
    Teaching.model_validate(r['conversations'][0]['response'])
    assert len(r['answers']) == 1
    r = client.post(f'/reviews/{id}/retest', json={'question_id': q['id']}).json()
    retest = r['questions'][-1]
    assert retest['kind'] == 'retest' and retest['prompt'] != q['prompt']
    assert retest['concept'] == q['concept']
    assert client.post(f'/reviews/{id}/retest', json={'question_id': q['id']}).json()['questions'] == r['questions']
    client.post(f'/reviews/{id}/answers', json={'question_id': retest['id'], 'answer': 'Deny a non-owner access to private documents; public visibility and ownership must be checked.'})
    report = client.get(f'/reviews/{id}/report').json()
    assert report['retest_improvements'] == [{'concept': q['concept'], 'before': 'incorrect', 'after': 'correct'}]
    assert report['questions_answered'] == 2
    assert report['teaching_exchanges'] == 1
    assert client.get(f'/reviews/{id}').json()['answers'][-1]['evaluation']['verdict'] == 'correct'
    reopened = Store(client.app.state.service.store.path)
    assert len(reopened.get(id).answers) == 2


def test_independent_teaching(client):
    r = create(client)
    r = client.post(f"/reviews/{r['id']}/teach", json={'concept': 'search.py', 'message': 'What is the complexity?'}).json()
    assert r['status'] == 'teaching'
    assert not r['questions'] and not r['answers']
    report = client.get(f"/reviews/{r['id']}/report").json()
    assert report['concepts_understood'] == []


def test_challenge_followup(client):
    r = create(client)
    id = r['id']
    q = client.post(f'/reviews/{id}/questions').json()['questions'][0]
    assert client.post(f'/reviews/{id}/answers', json={'question_id': q['id'], 'answer': 'owner', 'challenge': True}).status_code == 409
    r = client.post(f'/reviews/{id}/answers', json={'question_id': q['id'], 'answer': 'owner'}).json()
    assert r['questions'][-1]['kind'] == 'followup'
    r = client.post(f'/reviews/{id}/answers', json={'question_id': q['id'], 'answer': 'deny non-owner private access', 'challenge': True}).json()
    assert r['answers'][-1]['challenge']
    assert r['answers'][-1]['evaluation']['verdict'] == 'correct'


def test_errors(client, monkeypatch):
    assert client.get('/health').status_code == 200
    assert client.get('/reviews/missing').status_code == 404
    assert client.post('/reviews', json={'url': 'https://evil.com/a/b'}).status_code == 422
    r = create(client)
    assert client.post(f"/reviews/{r['id']}/answers", json={'question_id': 'missing', 'answer':'x'}).status_code == 404
    assert client.post(f"/reviews/{r['id']}/teach", json={'concept': 'x', 'message':''}).status_code == 422
    from ownit.llm import LLM
    monkeypatch.delenv('DARTMOUTH_API_KEY', raising=False)
    with pytest.raises(HTTPException) as err:
        LLM().generate(Evaluation, 'grade', {})
    assert err.value.status_code == 503


def test_redaction(monkeypatch):
    monkeypatch.setenv('DARTMOUTH_API_KEY', 'my-actual-key')
    text = redact('my-actual-key token="sensitive" sk-abcdefghijklmnop -----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----')
    assert 'my-actual-key' not in text and 'sensitive' not in text and 'abcdefghijklmnop' not in text and 'abc' not in text
    assert not safe_path('.env') and not safe_path('config/credentials.json')
    assert 'long password' not in redact('password="long password"')
    assert 'json-secret' not in redact('{"token": "json-secret"}')
    assert redact('-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----').count('\n') == 2


class FakeLLM:
    """Returns typed, realistic model outputs; verifies live orchestration separately from demo."""
    def __init__(self):
        self.calls = []
    def generate(self, schema, prompt, context):
        self.calls.append((schema, prompt, context))
        a = demo.analysis(demo.snapshot('initial', None))
        if schema == Analysis:
            return a
        if schema == QuestionSet:
            if 'retest_concept' in context:
                c = next(c for c in a.learning_objectives if c.name == context['retest_concept'])
                return QuestionSet(questions=[demo.question(c, 'temp', kind='retest')])
            return QuestionSet(questions=[demo.question(c, str(i)) for i,c in enumerate(a.learning_objectives)])
        if schema == Evaluation:
            return Evaluation(verdict='incorrect', feedback='Trace the ownership condition.', knowledge_gap='Authorization boundary', followup=None, evidence=a.components[0].evidence)
        if schema == Teaching:
            return demo.teach(a.learning_objectives[0])
        raise AssertionError(schema)


def test_mocked_live_agents(tmp_path, monkeypatch):
    monkeypatch.setattr(GitHub, 'fetch', lambda self, *args: demo.snapshot('initial', None))
    model = FakeLLM()
    with TestClient(create_app(str(tmp_path/'live.db'), model)) as c:
        r = c.app.state.service.create(CreateReview(url='https://github.com/acme/code')).model_dump()
        assert not r['demo']
        id = r['id']
        q = c.post(f'/reviews/{id}/questions').json()['questions'][0]
        assert c.post(f'/reviews/{id}/answers', json={'question_id':q['id'], 'answer':'wrong'}).status_code == 200
        assert c.post(f'/reviews/{id}/teach', json={'question_id':q['id'], 'concept':q['concept'], 'message':'explain'}).status_code == 200
        assert c.post(f'/reviews/{id}/retest', json={'question_id':q['id']}).status_code == 200
        assert [x[0] for x in model.calls] == [Analysis, QuestionSet, Evaluation, Teaching, QuestionSet]


@pytest.mark.parametrize('code,expected', [(404,404), (403,429), (429,429), (500,502)])
def test_github_errors(code, expected):
    import httpx
    gh = GitHub()
    gh.client.close()
    gh.client = httpx.Client(base_url='https://api.github.com', transport=httpx.MockTransport(lambda req: httpx.Response(code, json={})))
    with pytest.raises(HTTPException) as err:
        gh.get('/repos/a/b')
    assert err.value.status_code == expected
    gh.close()
