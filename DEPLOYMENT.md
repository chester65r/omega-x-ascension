# OMEGA-X ASCENSION deployment guide

The maintained instructions are in omega-x-ascension/docs/DEPLOYMENT.md.

Use `python omega-x-ascension/scripts/generate_env.py` to create unique secrets, then configure a model provider with `python omega-x-ascension/scripts/configure_provider.py`. Never copy example secrets into a live deployment and never commit `.env`.

The API port is bound to loopback by default. Put remote access behind HTTPS, authentication, and a firewall. Computer execution is disabled by default and, when explicitly enabled, is routed to the separate network-isolated sandbox container. This is not a hardened per-job VM boundary for untrusted multi-tenant workloads.
