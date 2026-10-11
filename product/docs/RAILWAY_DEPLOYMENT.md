# Railway deployment notes

Railway deployment is **prepared but not performed**. This session has no Railway token or authenticated Railway connector, and no database, project, domain, or service has been created.

## Recommended setup when Railway access is available

Railway's current documentation describes `railway.json`/`railway.toml` Config as Code as deprecated and identifies `.railway/railway.ts` IaC as the replacement. For this first release, avoid adding a legacy config-as-code file. Create a fresh Railway project and PostgreSQL service, then create an API service from the selected GitHub repository and the implementation branch after reviewing its diff. Configure the service root directory as `product/backend`; this prevents the unrelated repository tree from being used as the app source. Railway can detect the Dockerfile in that directory.

Link the API service's `DATABASE_URL` to the actual PostgreSQL service's connection URL through Railway's variable-reference picker; do not copy a fabricated URL. Set the following API variables as encrypted values where appropriate:

| Variable | Value source |
|---|---|
| `ENVIRONMENT` | `production` |
| `AUTO_CREATE_SCHEMA` | `false` |
| `JWT_SECRET` | Newly generated, unique secret of at least 32 characters |
| `DATABASE_URL` | Private Railway reference to the created PostgreSQL service |
| `OPENAI_COMPATIBLE_BASE_URL` | Supported provider's API base URL (defaults to OpenRouter if omitted) |
| `OPENAI_COMPATIBLE_API_KEY` | User-authorized provider credential |
| `AI_MODEL` | Model confirmed by the provider for that key and account |

The Dockerfile applies `alembic upgrade head`, then runs Uvicorn on Railway's assigned `PORT`. Configure the service health check as `/health/ready`. Expose a public API domain only after the variables are set; keep PostgreSQL private. Verify `GET /health/live`, `GET /health/ready`, account registration, cross-account isolation, a real provider response, and persistence across an API restart before calling the deployment complete.

No cost estimate is asserted: Railway plan/resource pricing and model access depend on the user's actual account and selected region/model. Review Railway's live project billing and provider rates before creating paid resources.

## References

- [Railway FastAPI guide](https://docs.railway.com/guides/fastapi)
- [Railway Infrastructure as Code](https://docs.railway.com/infrastructure-as-code) — current guidance says Config as Code is deprecated and new services should use IaC or dashboard configuration.
