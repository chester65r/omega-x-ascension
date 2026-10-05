# OMEGA-X ASCENSION — Deployment Guide

This guide explains how to deploy OMEGA-X ASCENSION in production after local testing.

## Architecture

```
Load Balancer (Nginx/AWS ALB)
      ↓
API Service (FastAPI, 2+ replicas)
      ↓
  ┌─────┴──────┐
  ↓            ↓
Worker    Worker  (auto-scaled by job queue depth)
(LangGraph)(LangGraph)
  ↓            ↓
  └─────┬──────┘
      ↓
PostgreSQL (managed: AWS RDS, Render, Supabase)
      ↓
Redis (managed: AWS ElastiCache, Render, Upstash)
      ↓
Model Endpoint (OpenAI, Together AI, vLLM, Ollama)
```

## Prerequisites

- Docker image built and tagged
- PostgreSQL 14+ (managed or self-hosted)
- Redis 7+ (managed or self-hosted)
- At least 2 worker processes
- Model provider API keys (OpenAI, Together, etc.)

## Step 1: Build Production Image

### Option A: Local build and push

```bash
# Build
docker build -t your-registry/omega-x-ascension:v0.4.0 .

# Tag for your registry
docker tag your-registry/omega-x-ascension:v0.4.0 \
  your-registry/omega-x-ascension:latest

# Push
docker push your-registry/omega-x-ascension:v0.4.0
```

### Option B: GitHub Actions (recommended)

Add `.github/workflows/build.yml`:

```yaml
name: Build and Push
on:
  push:
    tags: ['v*']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: docker/setup-buildx-action@v2
      - uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v4
        with:
          context: ./omega-x-ascension
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}
            ghcr.io/${{ github.repository }}:latest
```

## Step 2: Set Up Infrastructure

### PostgreSQL

```bash
# AWS RDS
aws rds create-db-instance \
  --db-instance-identifier omega-x-prod \
  --db-instance-class db.t3.small \
  --engine postgres \
  --engine-version 16 \
  --master-username omega \
  --master-user-password <STRONG_PASSWORD> \
  --allocated-storage 50 \
  --storage-type gp3 \
  --multi-az
```

Or use managed services:
- **Render**: https://render.com/docs/databases
- **Supabase**: https://supabase.com/docs/guides/database
- **AWS RDS**: https://aws.amazon.com/rds/

### Redis

```bash
# AWS ElastiCache
aws elasticache create-cache-cluster \
  --cache-cluster-id omega-x-prod \
  --cache-node-type cache.t3.small \
  --engine redis \
  --engine-version 7.0
```

Or use:
- **Render**: https://render.com/docs/redis
- **Upstash**: https://upstash.com/
- **AWS ElastiCache**: https://aws.amazon.com/elasticache/

## Step 3: Environment Variables

Create production `.env` file or use secrets manager:

```env
# Database
OMEGA_DATABASE_URL=postgresql+asyncpg://omega_app:PASSWORD@prod-db.example.com:5432/omega
OMEGA_WORKER_DATABASE_URL=postgresql+asyncpg://omega_worker:PASSWORD@prod-db.example.com:5432/omega
OMEGA_CHECKPOINT_DATABASE_URL=postgresql://omega_checkpoint:PASSWORD@prod-db.example.com:5432/omega
OMEGA_MIGRATION_DATABASE_URL=postgresql+psycopg://omega:PASSWORD@prod-db.example.com:5432/omega

# Redis
OMEGA_REDIS_URL=redis://:PASSWORD@prod-redis.example.com:6379/0

# JWT
OMEGA_JWT_SECRET=<64-character-random-string>
OMEGA_JWT_ISSUER=omega-x-prod
OMEGA_JWT_AUDIENCE=omega-x-api
OMEGA_JWT_ALGORITHM=HS256

# Models
OMEGA_MODEL_PROVIDERS=[{"name":"openai","base_url":"https://api.openai.com/v1","api_key":"sk-...","model":"gpt-4-turbo","capabilities":["reasoning","planning","analysis","summarization","coding","research","mathematics"],"priority":100}]

# Logging
OMEGA_LOG_LEVEL=INFO
OMEGA_ENV=production

# Security
LANGGRAPH_STRICT_MSGPACK=true
```

## Step 4: Run Migrations

Before starting services, initialize the database:

```bash
docker run --rm \
  -e OMEGA_MIGRATION_DATABASE_URL="postgresql+psycopg://..." \
  -e OMEGA_APP_PASSWORD="..." \
  -e OMEGA_WORKER_PASSWORD="..." \
  -e OMEGA_CHECKPOINT_PASSWORD="..." \
  your-registry/omega-x-ascension:v0.4.0 \
  python scripts/migrate.py
```

## Step 5: Deploy API Service

### Docker Compose (single machine)

```yaml
version: '3.8'
services:
  api:
    image: your-registry/omega-x-ascension:v0.4.0
    command: uvicorn omega.main:app --host 0.0.0.0 --port 8000 --workers 4
    ports:
      - "8000:8000"
    environment:
      OMEGA_DATABASE_URL: "${OMEGA_DATABASE_URL}"
      OMEGA_REDIS_URL: "${OMEGA_REDIS_URL}"
      OMEGA_JWT_SECRET: "${OMEGA_JWT_SECRET}"
      OMEGA_MODEL_PROVIDERS: "${OMEGA_MODEL_PROVIDERS}"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/ready"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 60s
```

### Kubernetes (recommended for production)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: omega-x-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: omega-x-api
  template:
    metadata:
      labels:
        app: omega-x-api
    spec:
      containers:
      - name: api
        image: your-registry/omega-x-ascension:v0.4.0
        command: ["uvicorn", "omega.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
        ports:
        - containerPort: 8000
        env:
        - name: OMEGA_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: omega-secrets
              key: database-url
        - name: OMEGA_REDIS_URL
          valueFrom:
            secretKeyRef:
              name: omega-secrets
              key: redis-url
        - name: OMEGA_JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: omega-secrets
              key: jwt-secret
        - name: OMEGA_MODEL_PROVIDERS
          value: '[{"name":"openai","base_url":"https://api.openai.com/v1","api_key":"sk-...","model":"gpt-4-turbo","capabilities":["reasoning","planning","analysis","summarization","coding","research","mathematics"],"priority":100}]'
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 5
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
---
apiVersion: v1
kind: Service
metadata:
  name: omega-x-api
spec:
  selector:
    app: omega-x-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Heroku

```bash
# Create app
heroku create omega-x-ascension

# Set secrets
heroku config:set -a omega-x-ascension \
  OMEGA_DATABASE_URL="..." \
  OMEGA_REDIS_URL="..." \
  OMEGA_JWT_SECRET="..."

# Deploy
git push heroku main
```

## Step 6: Deploy Worker

The worker processes jobs from the PostgreSQL queue.

### Docker Compose

```yaml
worker:
  image: your-registry/omega-x-ascension:v0.4.0
  command: python -m omega.worker
  environment:
    OMEGA_WORKER_DATABASE_URL: "${OMEGA_WORKER_DATABASE_URL}"
    OMEGA_CHECKPOINT_DATABASE_URL: "${OMEGA_CHECKPOINT_DATABASE_URL}"
    OMEGA_REDIS_URL: "${OMEGA_REDIS_URL}"
    OMEGA_MODEL_PROVIDERS: "${OMEGA_MODEL_PROVIDERS}"
  restart: unless-stopped
  deploy:
    replicas: 2  # Run 2 workers in parallel
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: omega-x-worker
spec:
  replicas: 3  # Scale by adjusting replicas
  selector:
    matchLabels:
      app: omega-x-worker
  template:
    metadata:
      labels:
        app: omega-x-worker
    spec:
      containers:
      - name: worker
        image: your-registry/omega-x-ascension:v0.4.0
        command: ["python", "-m", "omega.worker"]
        env:
        - name: OMEGA_WORKER_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: omega-secrets
              key: worker-database-url
        - name: OMEGA_CHECKPOINT_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: omega-secrets
              key: checkpoint-database-url
        - name: OMEGA_REDIS_URL
          valueFrom:
            secretKeyRef:
              name: omega-secrets
              key: redis-url
        resources:
          requests:
            cpu: 1000m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 2Gi
```

## Step 7: Monitor and Scale

### Monitoring

```bash
# Prometheus metrics
curl http://localhost:8000/metrics

# PostgreSQL jobs queue depth
psql $OMEGA_MIGRATION_DATABASE_URL -c \
  "SELECT status, COUNT(*) FROM workflow_jobs GROUP BY status;"

# Worker health
curl http://localhost:8000/health/ready
```

### Auto-scaling (Kubernetes)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: omega-x-worker-autoscale
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: omega-x-worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## Security Considerations

### TLS/HTTPS

Use a reverse proxy (Nginx, Caddy, AWS ALB) to terminate TLS:

```nginx
upstream omega {
  server api:8000;
}

server {
  listen 443 ssl http2;
  server_name api.example.com;

  ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

  location / {
    proxy_pass http://omega;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location /health/ready {
    access_log off;
    proxy_pass http://omega;
  }
}
```

### JWT

- Use asymmetric signing (RS256) instead of HS256 for multi-service deployments
- Store JWT signing key in a secrets manager (AWS Secrets Manager, HashiCorp Vault)
- Rotate keys regularly

### Database

- Use PostgreSQL row-level security (enabled in Phase 3 migration)
- Restrict IP access to DB from API/worker only
- Enable SSL connections
- Use IAM authentication (AWS RDS)
- Regular backups

### Redis

- Enable AUTH with strong passwords
- Use TLS for connections
- Restrict IP access
- No persistence for caches, use persistence only for durable state

## Troubleshooting

### API not connecting to DB

```bash
# Check connection string
echo $OMEGA_DATABASE_URL

# Test from container
docker exec omega-x-api psql $OMEGA_DATABASE_URL -c "SELECT 1"
```

### Worker jobs stuck in LEASED

```bash
# Reset expired leases
psql $OMEGA_MIGRATION_DATABASE_URL -c "
  UPDATE workflow_jobs 
  SET status='QUEUED', lease_owner=NULL, lease_expires_at=NULL 
  WHERE status='LEASED' AND lease_expires_at < now();
"
```

### High memory usage in workers

- Reduce `max_attempts` in `database.py`
- Reduce batch size for model calls
- Monitor with `docker stats`

### Slow model inference

- Use faster model (smaller params)
- Add GPU support (CUDA in worker image)
- Use quantized model
- Increase worker replicas

## Next Steps

1. **Test locally**: Complete `LOCAL_SETUP.md` first
2. **Set up staging**: Deploy to a staging environment
3. **Load test**: Use `locust` or `k6` to simulate traffic
4. **Monitor**: Set up Prometheus + Grafana or use managed monitoring
5. **Document**: Create runbooks for common operations
6. **Automate**: Use GitHub Actions / GitLab CI for deployments
