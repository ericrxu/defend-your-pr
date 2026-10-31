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
    'Authorization boundary': ('What role does access control play in the document-tag service?', 'How does deciding document access support the program\'s overall purpose?'),
    'Stable tag deduplication': ('What is the tag-processing part responsible for in this program?', 'How does the tag-processing part contribute to the result returned to a user?'),
    'Visibility before aggregation': ('How do the program\'s main parts work together to turn documents into a tag list?', 'Which main stages connect the user\'s document request to the final tag output?'),
}


def question(concept, id, parent=None, kind='original'):
    return Question(id=id, concept=concept.name, prompt=PROMPTS[concept.name][kind == 'retest'], rubric=concept.explanation, evidence=concept.evidence, parent_id=parent, kind=kind)


def grade(q, answer):
    words = answer.lower()
    groups = {
        'Authorization boundary': [('owner', 'ownership', 'owns', 'their own', 'belongs to', 'permission', 'access', 'authorization'), ('private', 'public', 'shared', 'document'), ('deny', 'false', 'reject', 'leak', 'unsafe', 'only', 'blocked', 'cannot', "can't", 'protect', 'restrict')],
        'Stable tag deduplication': [('set', 'seen', 'duplicate', 'tag'), ('order', 'list', 'skip', 'once', 'unique', 'already', 'output', 'result'), ('o(t)', 'linear', 'o(n)', 'quadratic', 'o(t²)', 'o(n^2)', 'o(t^2)', 'faster', 'quick', 'efficient', 'clean')],
        'Visibility before aggregation': [('filter', 'visible', 'visibility'), ('auth', 'permission', 'can_read'), ('tag', 'aggregate')],
    }[q.concept]
    count = sum(any(w in words for w in group) for group in groups)
    verdict = 'uncertain' if '?' in words and count == 0 else 'correct' if count >= 2 else 'partially_correct' if count else 'incorrect'
    return Evaluation(verdict=verdict, feedback=f'Demo rule-based feedback: matched {count} of 3 reasoning signals; two signals are enough for the main idea. Compare your reasoning with the cited code; keyword matching can be wrong.', knowledge_gap=None if verdict == 'correct' else q.concept, followup='What responsibility does this part have in the overall document-to-tags workflow?' if verdict == 'partially_correct' else None, evidence=q.evidence)


def teach(concept):
    examples = {
        'Authorization boundary': ('Access control is the part that decides which documents a caller may use. The service relies on that decision before collecting tags, so it protects private information.', 'Separate deciding access from organizing tags; they have different responsibilities.', 'What does the rest of the program rely on the access-control part to decide?'),
        'Stable tag deduplication': ('The tag-processing part turns the allowed documents into a clean list of distinct tags. It organizes the result after access has been decided.', 'Think about the difference between selecting documents and preparing the final tag list.', 'What does tag processing contribute to the result the user receives?'),
        'Visibility before aggregation': ('The program receives a user and documents, checks access, selects visible documents, then collects their tags into the final result.', 'Describe the input, the filtering stage, and the output stage in order.', 'How do the access-control and tag-processing parts cooperate?'),
    }
    explanation, hint, checkpoint = examples.get(concept.name, (concept.explanation, 'Trace one concrete input through the cited code.', 'What changes in the output for an edge case?'))
    return Teaching(explanation='[Prerecorded demo tutor] ' + explanation, hint=hint, checkpoint=checkpoint, evidence=concept.evidence)
