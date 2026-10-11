# OMEGA-X ASCENSION deployment guide

The maintained instructions are in omega-x-ascension/docs/DEPLOYMENT.md.

Use `python omega-x-ascension/scripts/generate_env.py` to create unique secrets, then configure a model provider with `python omega-x-ascension/scripts/configure_provider.py`. Never copy example secrets into a live deployment and never commit `.env`.

The API port is bound to loopback by default. Put remote access behind HTTPS, authentication, and a firewall. Tenant-scoped workspace file operations may be enabled independently. Shell command execution is currently blocked by the sandbox service with HTTP 503, even if the API feature flag is enabled, because all tenant workspaces share one Unix identity. Do not remove this guard until per-tenant OS isolation is implemented and adversarially tested.
