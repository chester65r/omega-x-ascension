#!/usr/bin/env python3
"""
Generate a test JWT token for OMEGA-X ASCENSION API.

Usage:
    python3 TEST_JWT.py

Then use the token in API calls:
    curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/v1/runs
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4

try:
    import jwt
except ImportError:
    print("Error: PyJWT not installed. Run: pip install PyJWT")
    sys.exit(1)

def main():
    # Read .env to get JWT secret
    env_file = Path(".env")
    if not env_file.exists():
        print("Error: .env not found. Run: python3 omega-x-ascension/scripts/generate_env.py")
        sys.exit(1)
    
    env_content = env_file.read_text()
    
    # Extract JWT secret
    for line in env_content.split('\n'):
        if line.startswith("OMEGA_JWT_SECRET="):
            secret = line.split("=", 1)[1].strip()
            break
    else:
        print("Error: OMEGA_JWT_SECRET not found in .env")
        sys.exit(1)
    
    # Create token
    tenant_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    claims = {
        "sub": "test-user",
        "tenant_id": tenant_id,
        "scope": "runs:read runs:write runs:approve",
        "iss": "omega-x",
        "aud": "omega-x-api",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    
    token = jwt.encode(claims, secret, algorithm="HS256")
    
    print("=" * 70)
    print("OMEGA-X ASCENSION — Test JWT Token")
    print("=" * 70)
    print()
    print(f"Tenant ID:  {tenant_id}")
    print(f"Valid for:  1 hour")
    print(f"Scopes:     runs:read runs:write runs:approve")
    print()
    print("Token:")
    print()
    print(token)
    print()
    print("=" * 70)
    print("Usage:")
    print("=" * 70)
    print()
    print("1. List runs:")
    print(f'   curl -H "Authorization: Bearer {token[:40]}..." http://localhost:8000/v1/runs/550e8400-e29b-41d4-a716-446655440000')
    print()
    print("2. Create a run:")
    print(f'   curl -X POST http://localhost:8000/v1/runs \\')
    print(f'     -H "Authorization: Bearer {token[:40]}..." \\')
    print(f'     -H "Content-Type: application/json" \\')
    print(f'     -d \'{{"goal":"Analyze this","task_type":"reasoning"}}\'')
    print()
    print("3. Check health (no token needed):")
    print("   curl http://localhost:8000/health/ready")
    print()

if __name__ == "__main__":
    main()
