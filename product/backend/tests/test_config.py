from sqlalchemy.engine import make_url

from omega_api.config import normalize_database_url


def test_normalize_neon_asyncpg_url_drops_channel_binding_and_preserves_tls():
    normalized = normalize_database_url(
        'postgresql://api_user:example-password@db.example.test/app'
        '?channel_binding=require&sslmode=require'
    )

    parsed = make_url(normalized)
    assert parsed.drivername == 'postgresql+asyncpg'
    assert 'channel_binding' not in parsed.query
    assert parsed.query['sslmode'] == 'require'
