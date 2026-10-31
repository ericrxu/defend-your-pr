import httpx
import pytest
from fastapi import HTTPException
from ownit.auth import exchange_code


@pytest.mark.parametrize('error,expected', [
    ('incorrect_client_credentials', 'same OAuth App'),
    ('redirect_uri_mismatch', 'callback URL'),
    ('bad_verification_code', 'already used'),
    ('unverified_user_email', 'primary email'),
    ('unknown_provider_error', 'OAuth App configuration'),
])
def test_safe_actionable_oauth_errors(monkeypatch, error, expected):
    monkeypatch.setattr(httpx, 'post', lambda url, **kw: httpx.Response(200, request=httpx.Request('POST',url), json={'error':error, 'error_description':'sensitive-provider-detail', 'access_token':'do-not-expose'}))
    with pytest.raises(HTTPException) as raised:
        exchange_code('temporary-code','verifier','http://localhost:8000/auth/github/callback')
    assert raised.value.status_code == 502
    assert expected in raised.value.detail
    assert 'sensitive-provider-detail' not in raised.value.detail
    assert 'do-not-expose' not in raised.value.detail


def test_network_failure_explains_backend_connectivity(monkeypatch):
    def blocked(url, **kwargs):
        raise httpx.ConnectError('private-network-details')
    monkeypatch.setattr(httpx, 'post', blocked)
    with pytest.raises(HTTPException) as raised:
        exchange_code('temporary-code','verifier','http://localhost:8000/auth/github/callback')
    assert 'outbound HTTPS access' in raised.value.detail
    assert 'private-network-details' not in raised.value.detail


@pytest.mark.parametrize('payload', [{}, [], {'access_token':None}])
def test_invalid_token_responses_are_handled(monkeypatch,payload):
    monkeypatch.setattr(httpx, 'post', lambda url, **kw: httpx.Response(200,request=httpx.Request('POST',url),json=payload))
    with pytest.raises(HTTPException) as raised:
        exchange_code('code','verifier','http://localhost:8000/auth/github/callback')
    assert raised.value.status_code == 502
