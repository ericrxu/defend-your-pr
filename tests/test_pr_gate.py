import hashlib
import hmac
import json
import secrets
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from ownit import demo
from ownit.github import GitHub
from ownit.main import create_app
from ownit.models import Analysis, Evaluation, Question, QuestionSet, Teaching


class Model:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def generate(self, schema, prompt, context):
        self.calls += 1
        if self.fail:
            raise HTTPException(502, 'Model temporarily unavailable.')
        a = demo.analysis(demo.snapshot('modified', 'demo-v1'))
        if schema == Analysis:
            return a
        if schema == QuestionSet:
            concepts = a.learning_objectives
            if context.get('retest_concept'):
                concepts = [c for c in concepts if c.name == context['retest_concept']]
            return QuestionSet(questions=[demo.question(c, str(i), kind='retest' if context.get('retest_concept') else 'original') for i,c in enumerate(concepts)])
        if schema == Evaluation:
            return demo.grade(Question.model_validate(context['question']), context['answer'])
        if schema == Teaching:
            return demo.teach(a.learning_objectives[0])
        raise AssertionError(schema)


@pytest.fixture
def gate_env(monkeypatch, tmp_path):
    monkeypatch.setenv('GITHUB_TOKEN', 'github-server-token')
    monkeypatch.setenv('GITHUB_WEBHOOK_SECRET', 'webhook-test-secret')
    monkeypatch.setenv('OWNIT_REPOSITORIES', 'acme/app')
    monkeypatch.setenv('GITHUB_CLIENT_ID', 'client-id')
    monkeypatch.setenv('GITHUB_CLIENT_SECRET', 'client-secret')
    state = {'head':'a'*40, 'base':'b'*40, 'status':'open', 'author':42, 'private':False, 'publish_error':False}
    statuses = []

    def pull():
        return {'state':state['status'], 'head':{'sha':state['head']}, 'base':{'sha':state['base']}, 'user':{'id':state['author'], 'login':'author'}}

    def get(self, path):
        if path == '/user':
            return {'id':42,'login':'author'}
        if '/pulls/' in path:
            return pull()
        return {'private':state['private'], 'visibility':'private' if state['private'] else 'public'}

    def fetch(self, *args):
        data = demo.snapshot('modified','demo-v1')
        data.update(sha=state['head'], base_sha=state['base'])
        return data

    def status(self, repo, sha, verdict, url, description):
        if state['publish_error'] and verdict == 'success':
            raise HTTPException(502, 'GitHub status update failed.')
        statuses.append((repo,sha,verdict,url))

    monkeypatch.setattr(GitHub, 'get', get)
    monkeypatch.setattr(GitHub, 'fetch', fetch)
    monkeypatch.setattr(GitHub, 'set_status', status)
    model = Model()
    app = create_app(str(tmp_path/'gates.db'),model)
    with TestClient(app) as client:
        client.headers['Origin'] = 'http://localhost:3000'
        yield client, state, statuses, model, pull


def identity(client, id=42):
    token = secrets.token_urlsafe(24)
    client.app.state.service.store.put_token(token, 'session', {'id':id,'login':'author' if id==42 else 'other'},3600)
    client.cookies.set('ownit_session',token)


def hook(client, pull, **overrides):
    payload = {'action':'opened', 'repository':{'full_name':'acme/app','private':False}, 'number':1, 'pull_request':pull()}
    payload.update(overrides)
    body = json.dumps(payload).encode()
    signature = 'sha256=' + hmac.new(b'webhook-test-secret',body,hashlib.sha256).hexdigest()
    return client.post('/webhooks/github',content=body,headers={'X-GitHub-Event':'pull_request','X-Hub-Signature-256':signature,'Content-Type':'application/json'})


def prepared(env):
    client, state, statuses, model, pull = env
    response = hook(client,pull)
    assert response.status_code == 202, response.text
    job = client.get('/pull-requests/'+response.json()['job_id']).json()
    assert job['state'] == 'quiz_required', job
    identity(client)
    review = client.get('/reviews/'+job['review_id']).json()
    assert review['gate_id'] == job['id']
    return job, review


def answer_all(client, review, answer):
    for q in review['questions']:
        response = client.post(f"/reviews/{review['id']}/answers",json={'question_id':q['id'],'answer':answer})
        assert response.status_code == 200, response.text
    return client.get('/reviews/'+review['id']).json()


GOOD = 'Deny non-owner access to private documents. A set gives linear lookup while a list preserves order. Filter visibility through authorization before aggregating tags.'


def test_webhook_quiz_author_and_success(gate_env):
    client, state, statuses, model, pull = gate_env
    job, r = prepared(gate_env)
    assert statuses[-1][2] == 'pending'
    assert statuses[-1][3].endswith('?job='+job['id'])
    assert r['analysis']['review_type'] == 'change'
    assert all('rubric' not in q for q in r['questions'])
    r = answer_all(client,r,GOOD)
    response = client.post(f"/reviews/{r['id']}/complete")
    assert response.status_code == 200, response.text
    assert statuses[-1][1:3] == (state['head'],'success')
    assert client.get('/pull-requests/'+job['id']).json()['state'] == 'passed'


@pytest.mark.parametrize('answer', ['I do not know.', 'Could you explain?'])
def test_incorrect_or_uncertain_cannot_unlock(gate_env, answer):
    client, _, statuses, _, _ = gate_env
    job, r = prepared(gate_env)
    answer_all(client,r,answer)
    assert client.post(f"/reviews/{r['id']}/complete").status_code == 409
    assert not any(s[2]=='success' for s in statuses)
    q = r['questions'][0]
    client.post(f"/reviews/{r['id']}/teach",json={'concept':q['concept'],'question_id':q['id'],'message':'Teach me.'})
    assert client.post(f"/reviews/{r['id']}/complete").status_code == 409
    assert client.get('/pull-requests/'+job['id']).json()['state'] == 'quiz_required'


def test_wrong_author_and_csrf_are_rejected(gate_env):
    client, _, statuses, _, _ = gate_env
    job, r = prepared(gate_env)
    client.cookies.clear()
    assert client.get('/reviews/'+r['id']).status_code == 401
    identity(client,99)
    assert client.get('/reviews/'+r['id']).status_code == 403
    assert client.post('/reviews/'+r['id']+'/complete').status_code == 403
    identity(client)
    assert client.post('/reviews/'+r['id']+'/complete',headers={'Origin':'https://evil.example'}).status_code == 403
    assert not any(s[2]=='success' for s in statuses)


@pytest.mark.parametrize('change', ['head','base','status','author'])
def test_changed_pr_cannot_use_old_approval(gate_env, change):
    client, state, statuses, _, _ = gate_env
    job,r = prepared(gate_env)
    answer_all(client,r,GOOD)
    state[change] = {'head':'c'*40,'base':'d'*40,'status':'closed','author':99}[change]
    assert client.post('/reviews/'+r['id']+'/complete').status_code == 409
    assert client.get('/pull-requests/'+job['id']).json()['state'] == 'stale'
    assert not any(s[2]=='success' for s in statuses)


def test_new_push_gets_a_new_blocked_quiz(gate_env):
    client,state,statuses,_,pull = gate_env
    old,r = prepared(gate_env)
    answer_all(client,r,GOOD)
    assert client.post('/reviews/'+r['id']+'/complete').status_code == 200
    state['head']='c'*40
    response=hook(client,pull,action='synchronize')
    new=client.get('/pull-requests/'+response.json()['job_id']).json()
    assert new['id']!=old['id'] and new['state']=='quiz_required'
    assert statuses[-1][1:3] == (state['head'],'pending')
    assert client.get('/reviews/'+new['review_id']).json()['answers']==[]
    assert client.get('/pull-requests/'+old['id']).json()['state']=='stale'


def test_duplicate_delivery_reuses_quiz(gate_env):
    client,_,_,model,pull = gate_env
    job,r=prepared(gate_env)
    calls=model.calls
    response=hook(client,pull)
    assert response.json()['job_id']==job['id']
    assert model.calls==calls


def test_provider_failure_stays_blocked_and_can_retry(gate_env):
    client,_,statuses,model,pull=gate_env
    model.fail=True
    response=hook(client,pull)
    job=client.get('/pull-requests/'+response.json()['job_id']).json()
    assert job['state']=='error'
    assert not any(s[2]=='success' for s in statuses)
    identity(client)
    model.fail=False
    assert client.post('/pull-requests/'+job['id']+'/retry').status_code==202
    assert client.get('/pull-requests/'+job['id']).json()['state']=='quiz_required'


def test_github_write_failure_does_not_complete(gate_env):
    client,state,statuses,_,_=gate_env
    job,r=prepared(gate_env)
    answer_all(client,r,GOOD)
    state['publish_error']=True
    assert client.post('/reviews/'+r['id']+'/complete').status_code==502
    assert client.get('/reviews/'+r['id']).json()['status']!='completed'
    assert client.get('/pull-requests/'+job['id']).json()['state']!='passed'
    assert not any(s[2]=='success' for s in statuses)


def test_bad_signature_and_unconnected_repo(gate_env):
    client,_,_,model,pull=gate_env
    assert client.post('/webhooks/github',json={},headers={'X-Hub-Signature-256':'sha256=wrong'}).status_code==401
    assert hook(client,pull,repository={'full_name':'other/repo','private':False}).status_code==403
    assert hook(client,pull,repository={'full_name':'acme/app','private':True}).status_code==422
    assert model.calls==0


def test_manual_pr_requires_author(gate_env):
    client,_,_,_,_=gate_env
    body={'url':'https://github.com/acme/app/pull/1'}
    assert client.post('/pull-requests',json=body).status_code==401
    identity(client,99)
    assert client.post('/pull-requests',json=body).status_code==403
    identity(client)
    assert client.post('/pull-requests',json={'url':'https://github.com/acme/app'}).status_code==422
    assert client.post('/pull-requests',json=body).status_code==202


def test_oauth_state_pkce_and_author_identity(gate_env,monkeypatch):
    client,_,_,_,_=gate_env
    response=client.get('/auth/github',follow_redirects=False)
    query=parse_qs(urlparse(response.headers['location']).query)
    assert query['code_challenge_method']==['S256']
    state=query['state'][0]
    assert client.get('/auth/github/callback?state=invalid&code=x',follow_redirects=False).status_code==401
    monkeypatch.setattr(httpx,'post',lambda url,**kw:httpx.Response(200,request=httpx.Request('POST',url),json={'access_token':'temporary-oauth-token'}))
    response=client.get('/auth/github/callback',params={'state':state,'code':'test-code'},follow_redirects=False)
    assert response.status_code==307
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'temporary-oauth-token' not in str(response.headers)
    assert client.get('/auth/me').json()['user']['id']==42
    assert client.get('/auth/github/callback',params={'state':state,'code':'test-code'},follow_redirects=False).status_code==401
    assert client.get('/auth/github?job=//evil.example',follow_redirects=False).status_code==422


def test_queued_job_is_recoverable(gate_env):
    client,_,statuses,_,pull=gate_env
    gates=client.app.state.gates
    job=gates.record('acme/app',1,pull())
    assert gates.store.pending_gates()[0].id==job.id
    gates.recover()
    assert gates.get(job.id).state=='quiz_required'
    assert statuses[-1][2]=='pending'


def test_teaching_then_correct_retest_clears_gap(gate_env):
    client,_,statuses,_,_=gate_env
    job,r=prepared(gate_env)
    first=r['questions'][0]
    for q in r['questions']:
        response=client.post('/reviews/'+r['id']+'/answers',json={'question_id':q['id'],'answer':'I do not know.' if q['id']==first['id'] else GOOD})
        assert response.status_code==200
    assert client.post('/reviews/'+r['id']+'/complete').status_code==409
    client.post('/reviews/'+r['id']+'/teach',json={'question_id':first['id'],'concept':first['concept'],'message':'Explain the ownership change.'})
    response=client.post('/reviews/'+r['id']+'/retest',json={'question_id':first['id']})
    assert response.status_code==200
    retest=response.json()['questions'][-1]
    assert retest['prompt']!=first['prompt']
    assert client.post('/reviews/'+r['id']+'/answers',json={'question_id':retest['id'],'answer':GOOD}).status_code==200
    assert client.post('/reviews/'+r['id']+'/complete').status_code==200
    assert statuses[-1][2]=='success'
    report=client.get('/reviews/'+r['id']+'/report').json()
    assert report['knowledge_gaps']==[]
    assert report['retest_improvements'][0]['before']=='incorrect'


def test_partial_requires_a_correct_followup(gate_env):
    client,_,statuses,_,_=gate_env
    _,r=prepared(gate_env)
    first=r['questions'][0]
    response=client.post('/reviews/'+r['id']+'/answers',json={'question_id':first['id'],'answer':'owner'})
    assert response.json()['answers'][-1]['evaluation']['verdict']=='partially_correct'
    followup=response.json()['questions'][-1]
    for q in r['questions'][1:]:
        client.post('/reviews/'+r['id']+'/answers',json={'question_id':q['id'],'answer':GOOD})
    assert client.post('/reviews/'+r['id']+'/complete').status_code==409
    client.post('/reviews/'+r['id']+'/answers',json={'question_id':followup['id'],'answer':GOOD})
    assert client.post('/reviews/'+r['id']+'/complete').status_code==200
    assert statuses[-1][2]=='success'


def test_demo_pr_contains_diff_and_cannot_bypass_passing(gate_env):
    client,_,statuses,_,_=gate_env
    r=client.post('/reviews',json={'demo':True,'demo_pr':True}).json()
    assert r['analysis']['review_type']=='change'
    assert r['diff'] and set(r['analysis']['changed_files'])=={'auth.py','search.py'}
    r=client.post('/reviews/'+r['id']+'/questions').json()
    assert 'This PR' in r['questions'][0]['prompt']
    answer_all(client,r,'I do not know.')
    assert client.post('/reviews/'+r['id']+'/complete').status_code==409
    assert not statuses


def test_commit_status_wire_format():
    captured=[]
    def handler(request):
        captured.append((str(request.url),json.loads(request.content)))
        return httpx.Response(201,json={})
    github=GitHub('test-token')
    github.client.close()
    github.client=httpx.Client(base_url='https://api.github.com',transport=httpx.MockTransport(handler))
    github.set_status('acme/app','a'*40,'pending','https://ownit.example/?job=1','Take the quiz.')
    github.close()
    assert captured[0][0]=='https://api.github.com/repos/acme/app/statuses/'+'a'*40
    assert captured[0][1]['context']=='OwnIt / understanding'
    assert captured[0][1]['state']=='pending'


def test_failed_demo_retest_can_get_a_new_scenario(gate_env):
    client,_,_,_,_=gate_env
    r=client.post('/reviews',json={'demo':True,'demo_pr':True}).json()
    r=client.post('/reviews/'+r['id']+'/questions').json()
    q=r['questions'][0]
    client.post('/reviews/'+r['id']+'/answers',json={'question_id':q['id'],'answer':'I do not know.'})
    client.post('/reviews/'+r['id']+'/teach',json={'question_id':q['id'],'concept':q['concept'],'message':'Help.'})
    retest=client.post('/reviews/'+r['id']+'/retest',json={'question_id':q['id']}).json()['questions'][-1]
    client.post('/reviews/'+r['id']+'/answers',json={'question_id':retest['id'],'answer':'Still unsure.'})
    next_retest=client.post('/reviews/'+r['id']+'/retest',json={'question_id':retest['id']}).json()['questions'][-1]
    assert next_retest['id']!=retest['id']
    assert next_retest['prompt']!=retest['prompt']
    assert next_retest['parent_id']==q['id']


def test_returning_to_old_revision_does_not_reuse_old_answers(gate_env):
    client,state,_,_,pull=gate_env
    old,r=prepared(gate_env)
    answer_all(client,r,GOOD)
    assert client.post('/reviews/'+r['id']+'/complete').status_code==200
    state['head']='c'*40
    hook(client,pull,action='synchronize')
    state['head']='a'*40
    response=hook(client,pull,action='synchronize')
    current=client.get('/pull-requests/'+response.json()['job_id']).json()
    assert current['review_id']!=r['id']
    assert client.get('/reviews/'+current['review_id']).json()['answers']==[]
    assert client.post('/reviews/'+r['id']+'/complete').status_code==409


def test_incomplete_code_context_cannot_unlock(gate_env,monkeypatch):
    client,_,statuses,_,pull=gate_env
    original=client.app.state.service.create
    def incomplete(request):
        r=original(request)
        r.coverage_complete=False
        client.app.state.service.store.save(r)
        return r
    monkeypatch.setattr(client.app.state.service,'create',incomplete)
    response=hook(client,pull)
    gate=client.get('/pull-requests/'+response.json()['job_id']).json()
    assert gate['state']=='error'
    assert 'smaller' in gate['error']
    assert not any(s[2]=='success' for s in statuses)
