from __future__ import annotations
import os
from alembic import context
from sqlalchemy import engine_from_config, pool
from omega.adapters.database import Base

config = context.config
url = os.environ.get("OMEGA_MIGRATION_DATABASE_URL")
if not url:
    raise RuntimeError("OMEGA_MIGRATION_DATABASE_URL is required")
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction(): context.run_migrations()
else:
    connectable = engine_from_config(config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction(): context.run_migrations()
