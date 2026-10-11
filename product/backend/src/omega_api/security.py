import base64
import hashlib
import hmac
import json
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return _password_hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def create_access_token(user_id: str, secret: str, ttl_seconds: int, token_version: int = 0) -> str:
    now = int(time.time())
    header = _b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    payload = _b64(json.dumps({'sub': user_id, 'iat': now, 'exp': now + ttl_seconds, 'ver': token_version}, separators=(',', ':')).encode())
    signing_input = f'{header}.{payload}'.encode('ascii')
    signature = hmac.new(secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
    return f'{header}.{payload}.{_b64(signature)}'


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split('.')
        signing_input = f'{header_part}.{payload_part}'.encode('ascii')
        expected = hmac.new(secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature_part)):
            raise ValueError('Invalid token signature')
        header = json.loads(_unb64(header_part))
        payload = json.loads(_unb64(payload_part))
        if header != {'alg': 'HS256', 'typ': 'JWT'}:
            raise ValueError('Invalid token algorithm')
        if not isinstance(payload.get('sub'), str) or int(payload.get('exp', 0)) <= int(time.time()):
            raise ValueError('Expired or invalid token')
        if type(payload.get('ver', 0)) is not int or payload.get('ver', 0) < 0:
            raise ValueError('Invalid token version')
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('Invalid or expired access token') from exc
