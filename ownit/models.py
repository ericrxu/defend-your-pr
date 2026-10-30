from typing import Literal
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, model_validator


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(extra='forbid')


class Evidence(BaseModel):
    path: str
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Invalid line range")
        return self


class Concept(BaseModel):
    name: str
    explanation: str
    evidence: list[Evidence]


class Risk(BaseModel):
    level: Literal["low", "medium", "high"]
    description: str
    confirmed: bool
    evidence: list[Evidence]


class Analysis(BaseModel):
    review_type: Literal["initial", "change"]
    summary: str
    components: list[Concept]
    algorithms: list[Concept]
    apis_and_dependencies: list[str]
    data_flow: list[str]
    changed_files: list[str]
    changed_functions: list[str]
    impacts: list[str]
    risks: list[Risk]
    learning_objectives: list[Concept] = Field(min_length=1, max_length=12)
    limitations: list[str]


class Question(BaseModel):
    id: str
    concept: str
    prompt: str
    rubric: str
    evidence: list[Evidence]
    parent_id: str | None
    kind: Literal["original", "followup", "retest"]


class QuestionSet(BaseModel):
    questions: list[Question] = Field(min_length=1, max_length=7)


class Evaluation(BaseModel):
    verdict: Literal["correct", "partially_correct", "incorrect", "uncertain"]
    feedback: str
    knowledge_gap: str | None
    followup: str | None
    evidence: list[Evidence]


class Teaching(BaseModel):
    explanation: str
    hint: str
    checkpoint: str
    evidence: list[Evidence]


class CreateReview(BaseModel):
    url: str = Field(default="", max_length=500)
    demo: bool = False
    demo_version: Literal["initial", "modified"] = "initial"
    commit: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{7,40}$")


class AnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=12000)
    challenge: bool = False


class TeachRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    concept: str = Field(min_length=1, max_length=500)
    question_id: str | None = None


class RetestRequest(BaseModel):
    question_id: str


class Review(BaseModel):
    id: str
    repo: str
    sha: str
    base_sha: str | None
    demo: bool
    created_at: str
    status: Literal["analyzed", "testing", "teaching", "completed"]
    analysis: Analysis
    files: dict[str, str]
    diff: str
    questions: list[Question]
    answers: list[dict]
    conversations: list[dict]


class Report(BaseModel):
    review_id: str
    status: str
    questions_answered: int
    outcomes: dict[str, int]
    concepts_understood: list[str]
    knowledge_gaps: list[str]
    teaching_exchanges: int
    retest_improvements: list[dict]
    next_steps: list[str]
    evidence: list[Evidence]
