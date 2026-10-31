import pytest
from fastapi import HTTPException
from ownit import demo
from ownit.changes import changed_lines, assessment_context
from ownit.db import Store
from ownit.llm import LLM
from ownit.models import CreateReview, Evidence, QuestionSet, RetestRequest, AnswerRequest, TeachRequest
from ownit.service import Orchestrator
from ownit.agents import testing


def test_hunk_line_numbers_exclude_unchanged_code_in_changed_file():
    files = {'example.py':'header\nunchanged\nnew\nextra\ncontext\ndef original_helper(): pass\n'}
    diff = 'modified example.py\n@@ -2,3 +2,4 @@\n unchanged\n-old\n+new\n+extra\n context'
    assert changed_lines(diff, files) == {'example.py':{3,4}}


def test_added_file_and_multiple_hunks():
    files = {'new.py':'one\ntwo\n', 'other.py':'a\nb\nc\nd\ne\nf\n'}
    diff = 'added new.py\n@@ -0,0 +1,2 @@\n+one\n+two\nmodified other.py\n@@ -2 +2 @@\n-old\n+b\n@@ -5 +5 @@\n-old\n+e'
    assert changed_lines(diff, files) == {'new.py':{1,2},'other.py':{2,5}}


def test_unified_demo_diff_is_supported():
    data = demo.snapshot('modified','demo-v1')
    lines = changed_lines(data['diff'],data['files'])
    assert set(lines)=={'auth.py','search.py'}
    assert 1 not in lines['auth.py']  # The existing function declaration is context.
    assert {2,3,4} <= lines['auth.py']
    assert 2 in lines['search.py']  # Newly added seen set.


def test_removal_only_change_uses_surviving_head_anchor():
    assert changed_lines('modified a.py\n@@ -1,2 +1 @@\n first\n-removed',{'a.py':'first\n'}) == {'a.py':{1}}


@pytest.fixture
def service(tmp_path):
    return Orchestrator(Store(str(tmp_path/'scope.db')),LLM())


def test_structural_quiz_retains_unchanged_components_and_full_workflow(service):
    review = service.create(CreateReview(demo=True,demo_pr=True))
    context, scope = assessment_context(review,service.context(review))
    assert context['files'] == review.files
    assert context['analysis'] == review.analysis.model_dump()
    assert context['analysis']['data_flow']
    assert scope is None  # Evidence can cover any supplied part of the program.
    assert context['assessment_scope']['policy'] == 'program_structure'
    assert context['assessment_scope']['changed_head_lines']['auth.py']
    assert context['diff'] == review.diff


def test_demo_pr_includes_the_unchanged_orchestration_part(service):
    r = service.create(CreateReview(demo=True,demo_pr=True))
    r = service.generate(r.id)
    assert len(r.questions)==3
    assert {q.concept for q in r.questions} == {'Authorization boundary','Stable tag deduplication','Visibility before aggregation'}
    assert any(e.path == 'service.py' for q in r.questions for e in q.evidence)
    assert all('complexity' not in q.prompt and 'seen set' not in q.prompt for q in r.questions)


@pytest.mark.parametrize('path,start,end', [('service.py',1,7),('auth.py',1,1),('search.py',9,9)])
def test_model_structural_question_can_cite_existing_code(service,path,start,end):
    r=service.create(CreateReview(demo=True,demo_pr=True))
    q=demo.question(r.analysis.learning_objectives[0],'placeholder')
    q.evidence=[Evidence(path=path,start=start,end=end)]
    q.prompt = 'What responsibility does this part have in the overall program?'
    class StructuralModel:
        def generate(self,*args):
            return QuestionSet(questions=[q])
    service.llm=StructuralModel()
    r.demo=False
    service.store.save(r)
    result = service.generate(r.id)
    assert len(result.questions) == 1
    assert result.questions[0].evidence == q.evidence


def test_retest_can_use_unchanged_structure_with_valid_evidence(service):
    r=service.generate(service.create(CreateReview(demo=True,demo_pr=True)).id)
    q=r.questions[0]
    service.answer(r.id,AnswerRequest(question_id=q.id,answer='I do not know.'))
    service.teach(r.id,TeachRequest(question_id=q.id,concept=q.concept,message='Help me understand the new check.'))
    structural=demo.question(r.analysis.learning_objectives[0],'placeholder',kind='retest')
    structural.evidence=[Evidence(path='service.py',start=1,end=7)]
    class StructuralModel:
        def generate(self,*args):
            return QuestionSet(questions=[structural])
    service.llm=StructuralModel()
    r=service.get(r.id)
    r.demo=False
    service.store.save(r)
    result = service.retest(r.id,RetestRequest(question_id=q.id))
    assert result.questions[-1].kind == 'retest'
    assert result.questions[-1].concept == q.concept
    assert result.questions[-1].evidence[0].path == 'service.py'


@pytest.mark.parametrize('evidence', [Evidence(path='missing.py',start=1,end=1), Evidence(path='service.py',start=1,end=999)])
def test_structural_questions_still_require_real_source_references(service,evidence):
    r = service.create(CreateReview(demo=True,demo_pr=True))
    r.demo = False
    service.store.save(r)
    q = demo.question(r.analysis.learning_objectives[0],'placeholder')
    q.evidence = [evidence]
    class InvalidEvidence:
        def generate(self,*args):
            return QuestionSet(questions=[q])
    service.llm = InvalidEvidence()
    with pytest.raises(HTTPException) as error:
        service.generate(r.id)
    assert error.value.status_code == 502
    assert service.get(r.id).questions == []


@pytest.mark.parametrize('concept,answer', [
    ('Authorization boundary','Only the owner.'),
    ('Authorization boundary','Users can read their own or public documents.'),
    ('Stable tag deduplication','The set makes lookups faster.'),
    ('Stable tag deduplication','It remembers seen tags and skips repeats.'),
])
def test_short_plain_language_demo_answers_pass(concept,answer):
    a=demo.analysis(demo.snapshot('modified','demo-v1'))
    objective=next(c for c in a.learning_objectives if c.name==concept)
    result=demo.grade(demo.question(objective,'q'),answer)
    assert result.verdict=='correct'
    assert result.knowledge_gap is None


def test_empty_understanding_still_does_not_pass():
    a=demo.analysis(demo.snapshot('modified','demo-v1'))
    result=demo.grade(demo.question(a.learning_objectives[0],'q'),'I do not know.')
    assert result.verdict=='incorrect'


def test_overloaded_questions_are_simplified_before_use(service):
    r=service.create(CreateReview(demo=True,demo_pr=True))
    context,_=service.testing_context(r)
    long=demo.question(r.analysis.learning_objectives[0],'long')
    long.prompt='What does the new check allow? What is the exact complexity? How would you test every possible edge case?'
    short=long.model_copy(update={'prompt':'What access does the new ownership check allow?'})
    class Model:
        def __init__(self):
            self.requests=[]
        def generate(self,schema,prompt,request):
            self.requests.append(request)
            return QuestionSet(questions=[long if len(self.requests)==1 else short])
    model=Model()
    result=testing.questions(model,context)
    assert result[0].prompt==short.prompt
    assert len(model.requests)==2
    assert model.requests[0]['question_budget']==3
    assert model.requests[0]['assessment_style']=='program_structure'


def test_persistently_overloaded_questions_are_not_saved(service):
    r=service.create(CreateReview(demo=True,demo_pr=True))
    r.demo=False
    service.store.save(r)
    q=demo.question(r.analysis.learning_objectives[0],'bad')
    q.prompt='Explain the new change? Explain all old functions? List every algorithm and all its edge cases?'
    class Model:
        def generate(self,*args):
            return QuestionSet(questions=[q])
    service.llm=Model()
    with pytest.raises(HTTPException) as error:
        service.generate(r.id)
    assert error.value.status_code==502
    assert not service.get(r.id).questions
