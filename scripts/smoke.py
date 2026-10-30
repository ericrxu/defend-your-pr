"""Run against a local backend: python scripts/smoke.py [http://localhost:8000]."""
import sys
import httpx

base = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'
with httpx.Client(base_url=base, timeout=30) as client:
    def call(path, body=None):
        r = client.get(path) if body is None else client.post(path, json=body)
        r.raise_for_status()
        return r.json()

    assert call('/health')['status'] == 'ok'
    r = call('/reviews', {'demo': True})
    assert r['analysis']['review_type'] == 'initial'
    path = f"/reviews/{r['id']}"
    r = call(path + '/questions', {})
    q = r['questions'][0]
    r = call(path + '/answers', {'question_id': q['id'], 'answer': 'I do not know.'})
    assert r['answers'][-1]['evaluation']['verdict'] == 'incorrect'
    r = call(path + '/teach', {'question_id': q['id'], 'concept': q['concept'], 'message': 'Help me trace access for another owner.'})
    assert r['status'] == 'teaching'
    r = call(path + '/retest', {'question_id': q['id']})
    assert r['questions'][-1]['prompt'] != q['prompt']
    for question in r['questions']:
        if any(a['question_id'] == question['id'] for a in r['answers']):
            continue
        r = call(path + '/answers', {'question_id': question['id'], 'answer': 'Deny a non-owner private access. A set supports linear lookup; a list preserves order. Filter visibility through authorization before aggregating tags.'})
    report = call(path + '/report')
    assert report['retest_improvements'][0]['after'] == 'correct'
    assert report['teaching_exchanges'] == 1
    call(path + '/complete', {})
    change = call('/reviews', {'demo': True, 'demo_version': 'modified'})
    assert change['analysis']['review_type'] == 'change'
    independent = call(f"/reviews/{change['id']}/teach", {'concept': 'Stable tag deduplication', 'message': 'Explain the set optimization.'})
    assert not independent['answers']
    print(f"PASS: initial review, change review, independent teaching, test/teach/retest, report and completion. Review {r['id']}")
