"""Explicit prerecorded demo content. No LLM is called in this mode."""
import difflib
from pathlib import Path
from .models import Analysis, Concept, Evidence, Risk, Question, Evaluation, Teaching

ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def snapshot(version, baseline):
    files = {p.name: p.read_text() for p in (ROOT / version).glob('*.py')}
    base = baseline
    # Opening the initial fixture deliberately restarts the demo walkthrough.
    if version == "initial":
        base = None
    old = {p.name: p.read_text() for p in (ROOT / ('modified' if base == 'demo-v2' else 'initial')).glob('*.py')}
    changed = [p for p in files if files[p] != old[p]] if base else []
    diff = '\n'.join(''.join(difflib.unified_diff(old[p].splitlines(True), files[p].splitlines(True), fromfile='a/'+p, tofile='b/'+p)) for p in changed)
    return dict(sha='demo-v2' if version == 'modified' else 'demo-v1', base_sha=base, files=files, diff=diff, changed_files=changed, limitations=['Prerecorded offline fixture; demo grading uses transparent keyword rules, not an AI judgment.'])


def evidence(path, end):
    return [Evidence(path=path, start=1, end=end)]


def analysis(data):
    modified = data['sha'] == 'demo-v2'
    auth = Concept(name='Authorization boundary', explanation='can_read permits authenticated owners or public documents.' if modified else 'can_read only checks whether a user exists; it never checks ownership or visibility.', evidence=evidence('auth.py', 4 if modified else 3))
    algorithm = Concept(name='Stable tag deduplication', explanation='A set tracks membership in average O(1), while a list preserves first-seen order. Total average O(T) time and O(U) space.' if modified else 'List membership scans prior tags. With T unique tags, repeated scanning takes O(T²) time and O(T) space.', evidence=evidence('search.py', 9 if modified else 7))
    flow = Concept(name='Visibility before aggregation', explanation='list_tags filters documents with can_read, then passes visible documents to unique_tags. Tags can leak private information if authorization is incorrect.', evidence=evidence('service.py', 7))
    return Analysis(review_type='change' if data['base_sha'] else 'initial', summary='A Python document-tag service connects access control, visibility filtering, and stable deduplication.', components=[auth, flow], algorithms=[algorithm], apis_and_dependencies=['Python standard library only; callers supply user and document dictionaries.'], data_flow=['Caller provides user + documents', 'service.list_tags → auth.can_read for each document', 'Visible documents → search.unique_tags → ordered tag list'], changed_files=data['changed_files'], changed_functions=['can_read', 'unique_tags'] if data['changed_files'] else [], impacts=['Ownership check prevents private tag disclosure.', 'Set membership improves expected runtime while preserving order; tags must be hashable.'] if modified else ['Authorization failures expose private document tags through the service.'], risks=[Risk(level='medium' if modified else 'high', description='Dictionary keys and hashable tags are assumed; malformed data may raise errors.' if modified else 'Confirmed authorization flaw: any signed-in user can read any private document.', confirmed=not modified, evidence=auth.evidence)], learning_objectives=[auth, algorithm, flow], limitations=data['limitations'])


PROMPTS = {
    'Authorization boundary': ('Trace a signed-in non-owner reading a private document. What does can_read return, and what should a safe policy check?', 'A non-owner requests tags from a private document. Explain how ownership and public visibility should govern the result.'),
    'Stable tag deduplication': ('Explain the time and space cost of unique_tags. How would a set plus a list change performance and output order?', 'If every document adds a new tag, compare list membership with set membership and explain how to preserve first-seen order.'),
    'Visibility before aggregation': ('Trace list_tags from user and documents to output. Why must authorization happen before collecting tags?', 'How could private tags leak through list_tags, and which component must enforce visibility before aggregation?'),
}


def question(concept, id, parent=None, kind='original'):
    return Question(id=id, concept=concept.name, prompt=PROMPTS[concept.name][kind == 'retest'], rubric=concept.explanation, evidence=concept.evidence, parent_id=parent, kind=kind)


def grade(q, answer):
    words = answer.lower()
    groups = {
        'Authorization boundary': [('owner', 'ownership'), ('private', 'public'), ('deny', 'false', 'reject', 'leak', 'unsafe')],
        'Stable tag deduplication': [('set',), ('order', 'list'), ('o(t)', 'linear', 'o(n)', 'quadratic', 'o(t²)', 'o(n^2)', 'o(t^2)')],
        'Visibility before aggregation': [('filter', 'visible', 'visibility'), ('auth', 'permission', 'can_read'), ('tag', 'aggregate')],
    }[q.concept]
    count = sum(any(w in words for w in group) for group in groups)
    verdict = 'uncertain' if '?' in words and count == 0 else 'correct' if count == 3 else 'partially_correct' if count else 'incorrect'
    return Evaluation(verdict=verdict, feedback=f'Demo rule-based feedback: matched {count} of 3 reasoning signals. Compare your reasoning with the cited code; keyword matching can be wrong.', knowledge_gap=None if verdict == 'correct' else q.concept, followup='Use the cited function to walk through one concrete input and its result.' if verdict == 'partially_correct' else None, evidence=q.evidence)


def teach(concept):
    examples = {
        'Authorization boundary': ('Compare user id with owner_id and inspect public visibility. In the initial fixture, user is not None ignores both fields.', 'Try user={id: 2}, document={owner_id: 1, public: False}.', 'Which boolean conditions should allow this document, and what happens for an anonymous user?'),
        'Stable tag deduplication': ('A list preserves order but membership scans the accumulated list. A set accelerates membership; keeping a separate output list preserves the order.', 'Walk through tags [a, b, a]. Count each membership lookup.', 'Why does returning only the set lose an important output property?'),
        'Visibility before aggregation': ('service.list_tags calls can_read for each document before unique_tags sees it. A permissive authorization function leaks information even when aggregation is correct.', 'Follow one private document through both calls.', 'What assertion would a regression test make about the tags of a different owner?'),
    }
    explanation, hint, checkpoint = examples.get(concept.name, (concept.explanation, 'Trace one concrete input through the cited code.', 'What changes in the output for an edge case?'))
    return Teaching(explanation='[Prerecorded demo tutor] ' + explanation, hint=hint, checkpoint=checkpoint, evidence=concept.evidence)
