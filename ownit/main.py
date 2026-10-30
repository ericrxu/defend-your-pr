import os
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass
from .db import Store
from .llm import LLM, dartmouth_api_key
from .models import CreateReview, AnswerRequest, TeachRequest, RetestRequest, Report, Review, Question, PullRequestInput, PullRequestGate
from .service import Orchestrator, public_review
from .gates import Gates, verify_signature
from .auth import attach_auth
from .github import parse_url


class PublicQuestion(Question):
    rubric: str | None = None


class PublicReview(Review):
    questions: list[PublicQuestion]


def create_app(database=None, llm=None):
    store = Store(database or os.getenv('OWNIT_DB', 'data/ownit.db'))
    service = Orchestrator(store, llm or LLM(), os.getenv('GITHUB_TOKEN'))
    gates = Gates(service)
    @asynccontextmanager
    async def lifespan(app):
        pending = store.pending_gates()
        recovery = asyncio.create_task(asyncio.to_thread(gates.recover, pending))
        yield
        await recovery
    app = FastAPI(title='OwnIt', version='0.2.0', lifespan=lifespan)
    app.state.service = service
    app.state.gates = gates
    user, require_user = attach_auth(app, store)
    origin = os.getenv('FRONTEND_ORIGIN', 'http://localhost:3000')
    app.add_middleware(CORSMiddleware, allow_origins=[origin], allow_credentials=True, allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    def check_origin(request):
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'This action must come from the configured OwnIt frontend.')

    def access(id, request, mutation=False):
        review = service.get(id)
        gates.authorize(review, user(request))
        if review.gate_id and mutation:
            check_origin(request)
            if gates.get(review.gate_id).state not in {'quiz_required','passed'}:
                raise HTTPException(409, 'This checkpoint is not active. Open the quiz for the latest PR revision or retry its failed analysis.')
        return review

    @app.post('/pull-requests', response_model=PullRequestGate, status_code=202)
    def submit_pr(body: PullRequestInput, request: Request, background: BackgroundTasks):
        identity = require_user(request)
        check_origin(request)
        job = gates.enqueue(body.url, identity['id'])
        if job.state == 'queued':
            background.add_task(gates.process, job.id)
        return job

    @app.get('/pull-requests/{id}', response_model=PullRequestGate)
    def pull_request(id: str):
        return gates.get(id)

    @app.post('/pull-requests/{id}/retry', response_model=PullRequestGate, status_code=202)
    def retry(id: str, request: Request, background: BackgroundTasks):
        identity = require_user(request)
        check_origin(request)
        with store.lock:
            job = gates.get(id)
            if identity['id'] != job.author_id:
                raise HTTPException(403, 'Only the PR author can retry this checkpoint.')
            if job.state != 'error':
                raise HTTPException(409, 'Only a failed analysis can be retried. Changed PRs need a new checkpoint.')
            job.state, job.error = 'queued', None
            store.save_gate(job)
            background.add_task(gates.process, job.id)
            return job

    @app.post('/webhooks/github', status_code=202)
    async def webhook(request: Request, background: BackgroundTasks):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                raise HTTPException(413, 'Webhook payload exceeds 1 MB.')
        verify_signature(bytes(body), request.headers.get('x-hub-signature-256'))
        event = request.headers.get('x-github-event')
        if event == 'ping':
            return {'received':True}
        if event != 'pull_request':
            return {'ignored':True}
        try:
            payload = json.loads(body)
            if payload.get('action') not in {'opened','reopened','synchronize','ready_for_review','edited'}:
                return {'ignored':True}
            if payload['action'] == 'edited' and 'base' not in payload.get('changes', {}):
                return {'ignored':True}
            repo, number = payload['repository']['full_name'], payload['number']
            if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                raise ValueError('Invalid PR number')
            repo, parsed_number = parse_url(f'https://github.com/{repo}/pull/{number}')
            if parsed_number != number or payload['repository'].get('private', True):
                raise HTTPException(422, 'Only public pull-request webhooks are supported.')
            # Acknowledge without remote HTTP or model calls. The worker verifies
            # the current GitHub revision before analysis and before approval.
            job = gates.record(repo, number, payload['pull_request'])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(422, 'Invalid pull-request webhook payload.') from None
        if job.state == 'queued':
            background.add_task(gates.process, job.id)
        return {'received':True, 'job_id':job.id}

    @app.get('/health')
    def health():
        return {'status': 'ok', 'live_ai_configured': bool(dartmouth_api_key())}

    @app.get('/reviews')
    def history():
        return store.history()

    @app.post('/reviews', response_model=PublicReview, response_model_exclude_none=True)
    def create(request: CreateReview):
        if not request.demo:
            parse_url(request.url)
            raise HTTPException(409, 'Live reviews now start from /pull-requests after the PR author signs in with GitHub.')
        with store.lock:
            return public_review(service.create(request))

    @app.get('/reviews/{id}', response_model=PublicReview, response_model_exclude_none=True)
    def get(id: str, request: Request):
        return public_review(access(id, request))

    @app.post('/reviews/{id}/questions', response_model=PublicReview, response_model_exclude_none=True)
    def questions(id: str, request: Request):
        with store.lock:
            access(id, request, True)
            return public_review(service.generate(id))

    @app.post('/reviews/{id}/answers', response_model=PublicReview, response_model_exclude_none=True)
    def answers(id: str, body: AnswerRequest, request: Request):
        with store.lock:
            access(id, request, True)
            return public_review(service.answer(id, body))

    @app.post('/reviews/{id}/teach', response_model=PublicReview, response_model_exclude_none=True)
    def teach(id: str, body: TeachRequest, request: Request):
        with store.lock:
            access(id, request, True)
            return public_review(service.teach(id, body))

    @app.post('/reviews/{id}/retest', response_model=PublicReview, response_model_exclude_none=True)
    def retest(id: str, body: RetestRequest, request: Request):
        with store.lock:
            access(id, request, True)
            return public_review(service.retest(id, body))

    @app.post('/reviews/{id}/complete', response_model=PublicReview, response_model_exclude_none=True)
    def complete(id: str, request: Request):
        with store.lock:
            review = access(id, request, True)
            return public_review(gates.approve(review, user(request)) if review.gate_id else service.complete(id))

    @app.get('/reviews/{id}/report', response_model=Report)
    def report(id: str, request: Request):
        access(id, request)
        return service.report(id)

    return app


app = create_app()
