from __future__ import annotations
import secrets
from pathlib import Path

def secret(): return secrets.token_urlsafe(36)
owner, app, worker, checkpoint, redis, jwt = secret(), secret(), secret(), secret(), secret(), secret()
content=f'''OMEGA_ENV=development
POSTGRES_PASSWORD={owner}
OMEGA_APP_PASSWORD={app}
OMEGA_WORKER_PASSWORD={worker}
OMEGA_CHECKPOINT_PASSWORD={checkpoint}
REDIS_PASSWORD={redis}
OMEGA_MIGRATION_DATABASE_URL=postgresql+psycopg://omega:{owner}@postgres:5432/omega
OMEGA_DATABASE_URL=postgresql+asyncpg://omega_app:{app}@postgres:5432/omega
OMEGA_WORKER_DATABASE_URL=postgresql+asyncpg://omega_worker:{worker}@postgres:5432/omega
OMEGA_CHECKPOINT_DATABASE_URL=postgresql://omega_checkpoint:{checkpoint}@postgres:5432/omega
OMEGA_REDIS_URL=redis://:{redis}@redis:6379/0
OMEGA_JWT_SECRET={jwt}
OMEGA_JWT_ISSUER=omega-x
OMEGA_JWT_AUDIENCE=omega-x-api
OMEGA_JWT_ALGORITHM=HS256
OMEGA_MODEL_PROVIDERS=[]
OMEGA_LOG_LEVEL=INFO
LANGGRAPH_STRICT_MSGPACK=true
'''
path=Path('.env')
if path.exists(): raise SystemExit('.env already exists; refusing to overwrite secrets')
path.write_text(content); path.chmod(0o600)
print('Created .env with mode 0600. Back it up in a secret manager; never commit it.')
