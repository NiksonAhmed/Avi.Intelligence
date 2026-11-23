from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.audit import models as _audit_models  # noqa: F401  (registers tables on Base.metadata)
from app.core.config import get_settings
from app.data_management import models as _dm_models  # noqa: F401
from app.db.session import Base
from app.knowledge import models as _knowledge_models  # noqa: F401
from app.reports import models as _report_models  # noqa: F401
from app.studies import models as _study_models  # noqa: F401

config = context.config

# The database URL always comes from application settings (DATABASE_URL), never alembic.ini.
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # render_as_batch lets ALTER TABLE migrations work on SQLite too.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
