# init_db.py
#
# Run this ONCE to create all database tables.
#
# Usage:
#   uv run python init_db.py
# ---------------------------------------------------------------------------

import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """
    Imports all models so SQLAlchemy is aware of them,
    then creates all tables that don't already exist.
    """
    # -- Import engine and Base from database module
    from database import engine, Base  # noqa: F401

    # -- Import all models so they register with Base.metadata
    #    If you add a new model, import it here.
    import models.candidate   # noqa: F401
    import models.session     # noqa: F401
    import models.qa          # noqa: F401
    import models.report      # noqa: F401

    logger.info("Connecting to database…")

    async with engine.begin() as conn:
        logger.info("Creating tables…")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables created successfully.")

    # Log each table that was registered
    from database import Base as AppBase
    table_names = list(AppBase.metadata.tables.keys())
    logger.info(f"Registered tables: {table_names}")

    await engine.dispose()
    logger.info("Database connection closed.")


async def drop_all_tables() -> None:
    """
    DANGER: Drops ALL tables. Use only in development.
    Controlled by DROP_TABLES=true environment variable.
    """
    if os.getenv("DROP_TABLES", "false").lower() != "true":
        logger.warning(
            "drop_all_tables() called but DROP_TABLES != true. Skipping."
        )
        return

    from database import engine, Base  # noqa: F401

    import models.candidate   # noqa: F401
    import models.session     # noqa: F401
    import models.qa          # noqa: F401
    import models.report      # noqa: F401

    logger.warning("Dropping ALL tables — this is irreversible!")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All tables dropped.")

    await engine.dispose()


async def reset_db() -> None:
    """
    Drops all tables then recreates them.
    Useful during development / testing.
    Controlled by DROP_TABLES=true environment variable.
    """
    await drop_all_tables()
    await init_db()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    # Accept optional command-line argument:
    #   python init_db.py          → create tables
    #   python init_db.py reset    → drop + recreate (needs DROP_TABLES=true)
    command = sys.argv[1] if len(sys.argv) > 1 else "init"

    if command == "reset":
        logger.info("Command: RESET DATABASE")
        asyncio.run(reset_db())

    elif command == "drop":
        logger.info("Command: DROP ALL TABLES")
        asyncio.run(drop_all_tables())

    else:
        logger.info("Command: INIT DATABASE")
        asyncio.run(init_db())