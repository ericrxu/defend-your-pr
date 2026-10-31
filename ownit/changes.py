"""Describe PR changes while retaining the program context for structural quizzes."""
import re

HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
FILE = re.compile(r'^(?:added|modified|renamed|removed|copied|changed|unchanged) (.+)$')


def changed_lines(diff, files):
    additions, deletions = {}, {}
    path, head = None, None
    for line in diff.splitlines():
        header = FILE.match(line)
        if header:
            path, head = header[1], None
            continue
        if line.startswith('--- a/'):
            head = None
            continue
        if line.startswith('+++ '):
            path = line[4:].removeprefix('b/').split('\t', 1)[0]
            head = None
            continue
        hunk = HUNK.match(line)
        if hunk:
            head = int(hunk[1])
            continue
        if path is None or head is None:
            continue
        if line.startswith('+'):
            additions.setdefault(path, set()).add(head)
            head += 1
        elif line.startswith('-'):
            deletions.setdefault(path, set()).add(max(1, head))
        elif line.startswith(' '):
            head += 1
    result = {}
    for path in additions.keys() | deletions.keys():
        if path not in files:
            continue
        length = len(files[path].splitlines())
        # A removal-only hunk has no added line; its surviving head anchor is
        # still a change location, not permission to assess unrelated code.
        lines = additions.get(path) or {min(n, length) for n in deletions[path]}
        valid = {n for n in lines if 1 <= n <= length}
        if valid:
            result[path] = valid
    return result


def touches(evidence, lines):
    return any(evidence.start <= n <= evidence.end for n in lines.get(evidence.path, ()))


def assessment_context(review, full_context):
    lines = changed_lines(review.diff, review.files) if review.analysis.review_type == 'change' else {}
    return {**full_context, 'assessment_scope':{
        'policy':'program_structure',
        'topics':['overall purpose', 'main parts and responsibilities',
                  'cooperation between parts', 'input-to-output workflow'],
        'changed_head_lines':{path:sorted(numbers) for path,numbers in lines.items()},
        'guidance':'Use all supplied files and the architecture analysis. The diff identifies this revision but does not limit quiz topics or evidence to changed lines. Ask about overall understanding, not implementation details.',
    }}, None
