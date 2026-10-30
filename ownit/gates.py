"""GitHub pull-request checkpoints tied to an exact base/head revision."""
import hashlib
import hmac
import os
import uuid
import sqlite3
import threading
from fastapi import HTTPException
from .github import GitHub, parse_url
from .models import CreateReview, PullRequestGate

CHECK_NAME = 'OwnIt / understanding'


def verify_signature(body, signature):
    secret = os.getenv('GITHUB_WEBHOOK_SECRET', '')
    if not secret:
        raise HTTPException(503, 'Configure GITHUB_WEBHOOK_SECRET before enabling GitHub webhooks.')
    expected = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, 'Invalid webhook signature.')


class Gates:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.worker_lock = threading.Lock()

    def github(self):
        token = os.getenv('GITHUB_TOKEN')
        if not token:
            raise HTTPException(503, 'Configure a server GITHUB_TOKEN with Commit statuses write permission.')
        return GitHub(token)

    def allowed(self, repo):
        repositories = {r.strip().lower() for r in os.getenv('OWNIT_REPOSITORIES', '').split(',') if r.strip()}
        if repo.lower() not in repositories:
            raise HTTPException(403, 'This repository is not connected. Add its owner/repo to OWNIT_REPOSITORIES on the server.')

    def get(self, id):
        gate = self.store.gate(id)
        if gate is None:
            raise HTTPException(404, 'Pull-request checkpoint not found.')
        return gate

    def url(self, gate):
        return os.getenv('OWNIT_APP_URL', 'http://localhost:3000').rstrip('/') + '/?job=' + gate.id

    def enqueue(self, url, user_id=None):
        repo, number = parse_url(url)
        if number is None:
            raise HTTPException(422, 'Enter a GitHub pull-request URL, such as https://github.com/owner/repo/pull/123.')
        self.allowed(repo)
        github = self.github()
        try:
            metadata = github.get(f'/repos/{repo}')
            if metadata.get('private') or metadata.get('visibility', 'public') != 'public':
                raise HTTPException(422, 'Only public repositories are supported.')
            pr = github.get(f'/repos/{repo}/pulls/{number}')
        finally:
            github.close()
        if pr['state'] != 'open':
            raise HTTPException(409, 'Only open pull requests can be assessed.')
        if user_id is not None and pr['user']['id'] != user_id:
            raise HTTPException(403, 'Only the pull-request author can take this quiz.')
        return self.record(repo, number, pr)

    def record(self, repo, number, pr):
        self.allowed(repo)
        existing = self.store.find_gate(repo, number, pr['head']['sha'], pr['base']['sha'])
        if existing:
            if existing.state == 'stale':
                # Returning to an earlier SHA is still a new checkpoint. Old
                # review answers must not approve the replacement session.
                existing.state, existing.error, existing.review_id = 'queued', None, None
                self.store.save_gate(existing)
            return existing
        gate = PullRequestGate(id=uuid.uuid4().hex, repo=repo, number=number, sha=pr['head']['sha'], base_sha=pr['base']['sha'], author=pr['user']['login'], author_id=pr['user']['id'], state='queued')
        try:
            self.store.save_gate(gate)
        except sqlite3.IntegrityError:
            return self.store.find_gate(repo, number, gate.sha, gate.base_sha)
        return gate

    def assert_current(self, gate, github):
        self.allowed(gate.repo)
        pr = github.get(f'/repos/{gate.repo}/pulls/{gate.number}')
        if pr['state'] != 'open' or pr['head']['sha'] != gate.sha or pr['base']['sha'] != gate.base_sha or pr['user']['id'] != gate.author_id:
            gate.state = 'stale'
            gate.error = 'The pull request changed or closed. Open the checkpoint for its latest commit.'
            self.store.save_gate(gate)
            raise HTTPException(409, gate.error)

    def process(self, id):
        # A single-process MVP: serialization prevents duplicate webhook deliveries
        # from creating competing quizzes or losing state updates.
        with self.worker_lock:
            gate = self.get(id)
            if gate.state not in {'queued', 'analyzing'}:
                return
            github = None
            try:
                github = self.github()
                self.assert_current(gate, github)
                for old in self.store.gates_for_pr(gate.repo, gate.number):
                    if old.id != gate.id and old.state != 'stale':
                        old.state, old.error = 'stale', 'A newer PR revision has its own checkpoint. This quiz cannot approve it.'
                        self.store.save_gate(old)
                github.set_status(gate.repo, gate.sha, 'pending', self.url(gate), 'Author must pass the quiz for this pull request before merging.')
                gate.state, gate.error = 'analyzing', None
                self.store.save_gate(gate)
                if gate.review_id:
                    review = self.service.get(gate.review_id)
                else:
                    review = self.service.create(CreateReview(url=f'https://github.com/{gate.repo}/pull/{gate.number}'))
                    if review.sha != gate.sha or review.base_sha != gate.base_sha:
                        self.assert_current(gate, github)
                        raise HTTPException(409, 'The analyzed revision does not match this checkpoint. Retry the current pull request.')
                    review.gate_id = gate.id
                    self.store.save(review)
                    gate.review_id = review.id
                    self.store.save_gate(gate)
                if not review.coverage_complete:
                    raise HTTPException(422, 'This PR exceeds the supported diff/code context limits. Split it into smaller changes before requesting merge approval.')
                self.service.generate(review.id)
                self.assert_current(gate, github)
                gate.state = 'quiz_required'
                self.store.save_gate(gate)
            except Exception as error:
                if gate.state != 'stale':
                    gate.state = 'error'
                    gate.error = error.detail if isinstance(error, HTTPException) else 'Analysis could not finish. The author can retry; the merge check remains blocked.'
                    self.store.save_gate(gate)
            finally:
                if github:
                    github.close()

    def recover(self, pending=None):
        for gate in self.store.pending_gates() if pending is None else pending:
            self.process(gate.id)

    def authorize(self, review, user):
        if not review.gate_id:
            return
        gate = self.get(review.gate_id)
        if not user:
            raise HTTPException(401, 'Sign in with GitHub as the pull-request author to open this quiz.')
        if user['id'] != gate.author_id:
            raise HTTPException(403, 'Only the pull-request author can access this quiz.')

    def approve(self, review, user):
        self.authorize(review, user)
        self.service.assert_passed(review)
        gate = self.get(review.gate_id)
        if gate.review_id != review.id:
            raise HTTPException(409, 'This quiz was replaced by a fresh checkpoint. Open the current quiz for this PR.')
        github = self.github()
        try:
            self.assert_current(gate, github)
            # Publish only after verifying every concept and the live PR revision.
            # A concurrent push receives a different SHA and cannot inherit this status.
            github.set_status(gate.repo, gate.sha, 'success', self.url(gate), 'PR author passed the code-understanding quiz for this commit.')
        finally:
            github.close()
        result = self.service.complete(review.id)
        gate.state, gate.error = 'passed', None
        self.store.save_gate(gate)
        return result
