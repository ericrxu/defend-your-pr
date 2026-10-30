import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass
from .db import Store
from .llm import LLM, dartmouth_api_key
from .models import CreateReview, AnswerRequest, TeachRequest, RetestRequest, Report, Review, Question
from .service import Orchestrator, public_review


class PublicQuestion(Question):
    rubric: str | None = None


class PublicReview(Review):
    questions: list[PublicQuestion]


def create_app(database=None, llm=None):
    store = Store(database or os.getenv('OWNIT_DB', 'data/ownit.db'))
    service = Orchestrator(store, llm or LLM(), os.getenv('GITHUB_TOKEN'))
    app = FastAPI(title='OwnIt', version='0.1.0')
    app.state.service = service
    app.add_middleware(CORSMiddleware, allow_origins=[os.getenv('FRONTEND_ORIGIN', 'http://localhost:3000')], allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @app.get('/health')
    def health():
        return {'status': 'ok', 'live_ai_configured': bool(dartmouth_api_key())}

    @app.get('/reviews')
    def history():
        return store.history()

    @app.post('/reviews', response_model=PublicReview, response_model_exclude_none=True)
    def create(request: CreateReview):
        with store.lock:
            return public_review(service.create(request))

    @app.get('/reviews/{id}', response_model=PublicReview, response_model_exclude_none=True)
    def get(id: str):
        return public_review(service.get(id))

    @app.post('/reviews/{id}/questions', response_model=PublicReview, response_model_exclude_none=True)
    def questions(id: str):
        with store.lock:
            return public_review(service.generate(id))

    @app.post('/reviews/{id}/answers', response_model=PublicReview, response_model_exclude_none=True)
    def answers(id: str, request: AnswerRequest):
        with store.lock:
            return public_review(service.answer(id, request))

    @app.post('/reviews/{id}/teach', response_model=PublicReview, response_model_exclude_none=True)
    def teach(id: str, request: TeachRequest):
        with store.lock:
            return public_review(service.teach(id, request))

    @app.post('/reviews/{id}/retest', response_model=PublicReview, response_model_exclude_none=True)
    def retest(id: str, request: RetestRequest):
        with store.lock:
            return public_review(service.retest(id, request))

    @app.post('/reviews/{id}/complete', response_model=PublicReview, response_model_exclude_none=True)
    def complete(id: str):
        with store.lock:
            return public_review(service.complete(id))

    @app.get('/reviews/{id}/report', response_model=Report)
    def report(id: str):
        return service.report(id)

    return app


app = create_app()
