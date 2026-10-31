"""Limit PR assessments to changed head lines, retaining nearby context only."""
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
    if review.analysis.review_type != 'change':
        return full_context, None
    lines = changed_lines(review.diff, review.files)
    facts = review.analysis.model_dump()
    for key in ('components', 'algorithms', 'learning_objectives', 'risks'):
        original = getattr(review.analysis, key)
        facts[key] = [item.model_dump() for item in original if any(touches(ev, lines) for ev in item.evidence)]
    facts['summary'] = 'Assessment covers only the additions and modifications in the supplied PR diff.'
    facts['data_flow'], facts['apis_and_dependencies'] = [], []
    snippets = {}
    for path, changed in lines.items():
        source = review.files[path].splitlines()
        visible = {n for line in changed for n in range(max(1,line-2), min(len(source),line+2)+1)}
        snippets[path] = '\n'.join(f'{n}: {source[n-1]}' for n in sorted(visible))
    head_only_diff = '\n'.join(path + '\n' + '\n'.join(f'+{n}: {review.files[path].splitlines()[n-1]}' for n in sorted(changed)) for path,changed in lines.items())
    return {'analysis':facts, 'files':snippets, 'diff':head_only_diff,
            'assessment_scope':{'policy':'new_changes_only', 'changed_head_lines':{p:sorted(ns) for p,ns in lines.items()},
                'context_only':'Nearby unchanged lines and minus lines are context, never independent quiz topics. Snippet prefixes are original head line numbers.'}}, lines
