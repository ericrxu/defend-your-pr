"""GitHub identity verification. OAuth access tokens are never persisted."""
import base64
import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import urlencode
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from .github import GitHub

OAUTH_ERRORS = {
    'incorrect_client_credentials': 'GitHub rejected the OAuth client credentials. Check GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET belong to the same OAuth App, then restart the backend.',
    'redirect_uri_mismatch': 'GitHub rejected the callback URL. Set the OAuth App callback to OWNIT_API_URL/auth/github/callback and restart sign-in.',
    'bad_verification_code': 'The GitHub sign-in code expired or was already used. Return to OwnIt and click Sign in with GitHub again; do not refresh the callback page.',
    'unverified_user_email': 'Verify your primary email address in GitHub settings, then start sign-in again.',
}


def exchange_code(code, verifier, redirect_uri):
    try:
        response = httpx.post('https://github.com/login/oauth/access_token', headers={'Accept':'application/json'}, json={'client_id':os.getenv('GITHUB_CLIENT_ID'), 'client_secret':os.getenv('GITHUB_CLIENT_SECRET'), 'redirect_uri':redirect_uri, 'code':code, 'code_verifier':verifier}, timeout=30)
    except httpx.RequestError:
        raise HTTPException(502, 'OwnIt cannot reach GitHub to finish sign-in. Run the backend with outbound HTTPS access, then return to OwnIt and start sign-in again.') from None
    try:
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPStatusError, ValueError):
        raise HTTPException(502, 'GitHub returned an unsuccessful or invalid token response. Return to OwnIt and start sign-in again.') from None
    if not isinstance(payload, dict):
        raise HTTPException(502, 'GitHub returned an invalid token response. Start sign-in again.')
    if payload.get('error'):
        # Never expose provider error descriptions, credentials or access tokens.
        message = OAUTH_ERRORS.get(payload['error'], 'GitHub rejected the sign-in exchange. Check the OAuth App configuration, then start sign-in again.')
        raise HTTPException(502, message)
    token = payload.get('access_token')
    if not isinstance(token, str) or not token:
        raise HTTPException(502, 'GitHub did not issue an access token. Check the OAuth App configuration, then start sign-in again.')
    return token


def attach_auth(app, store):
    def user(request):
        token = request.cookies.get('ownit_session', '')
        return store.read_token(token, 'session') if token else None

    def require_user(request):
        identity = user(request)
        if identity is None:
            raise HTTPException(401, 'Sign in with GitHub to take your pull-request quiz.')
        return identity

    def callback_url():
        return os.getenv('OWNIT_API_URL', 'http://localhost:8000').rstrip('/') + '/auth/github/callback'

    def secure():
        return callback_url().startswith('https://')

    @app.get('/auth/me')
    def me(request: Request):
        return {'user': user(request), 'configured': bool(os.getenv('GITHUB_CLIENT_ID') and os.getenv('GITHUB_CLIENT_SECRET'))}

    @app.get('/auth/github')
    def login(job: str = ''):
        client_id = os.getenv('GITHUB_CLIENT_ID')
        if not client_id or not os.getenv('GITHUB_CLIENT_SECRET'):
            raise HTTPException(503, 'Configure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to verify PR author identity.')
        if job and not re.fullmatch(r'[0-9a-f]{32}', job):
            raise HTTPException(422, 'Invalid checkpoint identifier.')
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        store.put_token(state, 'oauth', {'job':job, 'verifier':verifier}, 600)
        response = RedirectResponse('https://github.com/login/oauth/authorize?' + urlencode({'client_id':client_id, 'redirect_uri':callback_url(), 'scope':'read:user', 'state':state, 'code_challenge':challenge, 'code_challenge_method':'S256'}))
        response.set_cookie('ownit_oauth', state, httponly=True, secure=secure(), samesite='lax', max_age=600)
        return response

    @app.get('/auth/github/callback')
    def callback(request: Request, code: str = '', state: str = ''):
        cookie = request.cookies.get('ownit_oauth', '')
        if not state or not cookie or not hmac.compare_digest(cookie, state):
            raise HTTPException(401, 'GitHub sign-in state did not match. Start sign-in again.')
        data = store.read_token(state, 'oauth', consume=True)
        if not data or not code:
            raise HTTPException(401, 'GitHub sign-in expired or was declined. Start sign-in again.')
        github = None
        token = exchange_code(code, data['verifier'], callback_url())
        try:
            github = GitHub(token)
            account = github.get('/user')
            identity = {'id':int(account['id']), 'login':account['login']}
        except (httpx.HTTPError, HTTPException, ValueError, KeyError, TypeError):
            raise HTTPException(502, 'GitHub issued a token, but OwnIt could not read your GitHub identity. Check outbound access to api.github.com, then start sign-in again.') from None
        finally:
            if github:
                github.close()
        session = secrets.token_urlsafe(32)
        store.put_token(session, 'session', identity, 8*60*60)
        target = os.getenv('OWNIT_APP_URL', 'http://localhost:3000').rstrip('/') + '/'
        if data['job']:
            target += '?job=' + data['job']
        response = RedirectResponse(target)
        response.delete_cookie('ownit_oauth')
        response.set_cookie('ownit_session', session, httponly=True, secure=secure(), samesite='lax', max_age=8*60*60)
        return response

    return user, require_user
