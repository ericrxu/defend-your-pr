import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from . import demo
from .agents import analysis, testing, teaching
from .github import GitHub, parse_url
from .models import Review, Question, Report
from .security import redact
from .changes import assessment_context


def uid():
    return uuid.uuid4().hex


class Orchestrator:
    def __init__(self, store, llm, token=None):
        self.store, self.llm, self.token = store, llm, token

    def get(self, id):
        review = self.store.get(id)
        if review is None:
            raise HTTPException(404, 'Review not found.')
        return review

    def verify_evidence(self, items, files):
        for ev in items:
            if ev.path not in files or ev.end > len(files[ev.path].splitlines()):
                raise HTTPException(502, 'AI returned a code reference outside the supplied context. Retry.')

    def create(self, request):
        repo, pr = ('ownit-demo/document-tags', None) if request.demo else parse_url(request.url)
        baseline = self.store.baseline(repo, request.demo)
        if request.demo:
            data = demo.snapshot('modified', 'demo-v1') if request.demo_pr else demo.snapshot(request.demo_version, baseline)
        else:
            github = GitHub(self.token)
            try:
                data = github.fetch(repo, pr, request.commit, baseline)
            finally:
                github.close()
        data['review_type'] = 'change' if data['base_sha'] else 'initial'
        result = demo.analysis(data) if request.demo else analysis.analyze(self.llm, data)
        self.verify_evidence([e for c in result.components + result.algorithms + result.learning_objectives for e in c.evidence] + [e for risk in result.risks for e in risk.evidence], data['files'])
        review = Review(id=uid(), repo=repo, sha=data['sha'], base_sha=data['base_sha'], demo=request.demo, created_at=datetime.now(timezone.utc).isoformat(), status='analyzed', analysis=result, files=data['files'], diff=data['diff'], questions=[], answers=[], conversations=[])
        review.coverage_complete = data.get('coverage_complete', True)
        self.store.save(review)
        return review

    def context(self, r):
        return {'analysis': r.analysis.model_dump(), 'files': r.files, 'diff': r.diff}

    def testing_context(self, r):
        return assessment_context(r, self.context(r))

    def verify_question_evidence(self, question, r):
        self.verify_evidence(question.evidence, r.files)

    def mutable(self, r):
        if r.status == 'completed':
            raise HTTPException(409, 'This review is completed. Start a new review to assess more changes.')

    def generate(self, id):
        r = self.get(id)
        if r.questions:
            return r
        self.mutable(r)
        context, _ = self.testing_context(r)
        objectives = r.analysis.learning_objectives
        qs = [demo.question(c, uid()) for c in objectives] if r.demo else testing.questions(self.llm, context)
        if not qs:
            raise HTTPException(502, 'AI returned too few questions for the identified learning objectives. Retry.')
        if len({q.prompt for q in qs}) != len(qs) or len({q.concept for q in qs}) != len(qs):
            raise HTTPException(502, 'AI returned duplicate assessment concepts. Retry.')
        for q in qs:
            self.verify_question_evidence(q, r)
            q.id, q.parent_id, q.kind = uid(), None, 'original'
        r.questions, r.status = qs, 'testing'
        self.store.save(r)
        return r

    def question(self, r, id):
        q = next((q for q in r.questions if q.id == id), None)
        if q is None:
            raise HTTPException(404, 'Question not found in this review.')
        return q

    def answer(self, id, request):
        r = self.get(id)
        self.mutable(r)
        q = self.question(r, request.question_id)
        previous = [a for a in r.answers if a['question_id'] == q.id]
        if request.challenge and not previous:
            raise HTTPException(409, 'Attempt the question before challenging its evaluation.')
        if previous and not request.challenge:
            raise HTTPException(409, 'Question already answered. Challenge the evaluation or request a retest.')
        context, _ = self.testing_context(r)
        result = demo.grade(q, request.answer) if r.demo else testing.evaluate(self.llm, {**context, 'question': q.model_dump(), 'answer': redact(request.answer), 'challenge': request.challenge, 'previous_evaluations': previous})
        self.verify_evidence(result.evidence, r.files)
        r.answers.append({'id': uid(), 'question_id': q.id, 'answer': redact(request.answer), 'evaluation': result.model_dump(), 'challenge': request.challenge})
        if result.verdict == 'partially_correct' and result.followup and not any(item.kind == 'followup' and item.parent_id == q.id for item in r.questions):
            r.questions.append(Question(id=uid(), concept=q.concept, prompt=result.followup, rubric=q.rubric, evidence=q.evidence, parent_id=q.id, kind='followup'))
        r.status = 'testing'
        self.store.save(r)
        return r

    def teach(self, id, request):
        r = self.get(id)
        self.mutable(r)
        q = self.question(r, request.question_id) if request.question_id else None
        if q and q.concept != request.concept:
            raise HTTPException(422, 'The teaching concept must match the selected question.')
        concept = next((c for c in r.analysis.learning_objectives + r.analysis.components + r.analysis.algorithms if c.name == request.concept), None)
        if not concept and r.demo:
            concept = next((c for c in r.analysis.learning_objectives if any(e.path == request.concept for e in c.evidence)), None)
        if r.demo and not concept:
            raise HTTPException(422, 'Demo tutor supports the listed concepts and fixture files.')
        result = demo.teach(concept) if r.demo else teaching.teach(self.llm, {**self.context(r), 'concept': request.concept, 'question': q.model_dump() if q else None, 'answers': [a for a in r.answers if q and a['question_id'] == q.id], 'conversation': r.conversations[-12:], 'message': redact(request.message)})
        self.verify_evidence(result.evidence, r.files)
        r.conversations.append({'id': uid(), 'concept': q.concept if q else concept.name if concept else request.concept, 'question_id': q.id if q else None, 'message': redact(request.message), 'response': result.model_dump()})
        r.status = 'teaching'
        self.store.save(r)
        return r

    def retest(self, id, request):
        r = self.get(id)
        self.mutable(r)
        original = self.question(r, request.question_id)
        context, _ = self.testing_context(r)
        root = original
        while root.parent_id:
            root = self.question(r, root.parent_id)
        root_id = root.id
        if not any(a['question_id'] == original.id for a in r.answers):
            raise HTTPException(409, 'Answer the original question before retesting.')
        if not any(c['concept'] == original.concept for c in r.conversations):
            raise HTTPException(409, 'Use Teaching Mode for this concept before requesting a retest.')
        retests = [q for q in r.questions if q.kind == 'retest' and q.parent_id == root_id]
        existing = retests[-1] if retests else None
        if existing and not any(a['question_id'] == existing.id for a in r.answers):
            return r
        if r.demo:
            concept = next(c for c in r.analysis.learning_objectives if c.name == original.concept)
            q = demo.question(concept, uid(), root_id, 'retest')
            if retests:
                scenarios = {'Authorization boundary':'Compare an anonymous caller and an authenticated non-owner requesting a public document.', 'Stable tag deduplication':'Consider empty documents, all unique tags, and a non-hashable tag.', 'Visibility before aggregation':'Consider a mixture of public documents and another user\'s private documents sharing the same tag.'}
                q.prompt = f"Retest {len(retests)+1}: {scenarios[q.concept]} {q.prompt}"
        else:
            qs = testing.questions(self.llm, {**context, 'retest_concept': original.concept, 'previous_questions': [q.model_dump() for q in r.questions], 'answers': r.answers, 'teaching': r.conversations[-6:]})
            if len(qs) != 1:
                raise HTTPException(502, 'Retest must contain exactly one question. Retry.')
            q = qs[0]
            q.id, q.parent_id, q.kind, q.concept = uid(), root_id, 'retest', original.concept
        if q.prompt in {q.prompt for q in r.questions}:
            raise HTTPException(502, 'Retest repeated an existing question. Retry.')
        self.verify_question_evidence(q, r)
        r.questions.append(q)
        r.status = 'testing'
        self.store.save(r)
        return r

    def complete(self, id):
        r = self.get(id)
        self.assert_passed(r)
        r.status = 'completed'
        self.store.save(r)
        return r

    def assert_passed(self, r):
        answered = {a['question_id'] for a in r.answers}
        if not r.questions or any(q.id not in answered for q in r.questions):
            raise HTTPException(409, 'Answer all generated questions before completing the review.')
        latest = {}
        for answer in r.answers:
            latest[self.question(r, answer['question_id']).concept] = answer['evaluation']['verdict']
        required = {q.concept for q in r.questions if q.kind == 'original'}
        if not required or any(latest.get(concept) != 'correct' for concept in required):
            raise HTTPException(409, 'Quiz not passed. Demonstrate every assessed concept with a correct answer or retest; partial, incorrect and uncertain evaluations keep the checkpoint blocked.')

    def report(self, id):
        r = self.get(id)
        latest, concepts = {}, {}
        for a in r.answers:
            latest[a['question_id']] = a
            concepts[self.question(r, a['question_id']).concept] = a['evaluation']
        outcomes = {k: sum(a['evaluation']['verdict'] == k for a in latest.values()) for k in ('correct', 'partially_correct', 'incorrect', 'uncertain')}
        improvements = []
        for q in r.questions:
            if q.kind == 'retest' and q.id in latest and q.parent_id in latest:
                improvements.append({'concept': q.concept, 'before': latest[q.parent_id]['evaluation']['verdict'], 'after': latest[q.id]['evaluation']['verdict']})
        gaps = [k for k, ev in concepts.items() if ev['verdict'] != 'correct']
        return Report(review_id=id, status=r.status, questions_answered=len(latest), outcomes=outcomes, concepts_understood=[k for k, ev in concepts.items() if ev['verdict'] == 'correct'], knowledge_gaps=gaps, teaching_exchanges=len(r.conversations), retest_improvements=improvements, next_steps=[f'Revisit {g} using its code references and try a new scenario.' for g in gaps], evidence=[e for c in r.analysis.learning_objectives for e in c.evidence])


def public_review(r):
    result = r.model_dump()
    for q in result['questions']:
        q.pop('rubric')
    return result
