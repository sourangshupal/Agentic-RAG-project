import logging
import re
import socket
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from src.db.interfaces.base import BaseDatabase
from src.schemas.database.config import PostgreSQLSettings

logger = logging.getLogger(__name__)


def _force_ipv4_connect_arg(url: str) -> dict:
    """Resolve the DB hostname to an IPv4 address.

    psycopg2 supports passing both `host` (used for SSL SNI) and `hostaddr`
    (the actual IP to connect to). When `hostaddr` is an IPv4 address, the
    TCP connection bypasses IPv6 entirely — fixing deployments where IPv6 is
    not routed but DNS still returns AAAA records.
    """
    match = re.search(r"@([^/:@?]+)", url)
    if not match:
        return {}
    host = match.group(1)
    try:
        results = socket.getaddrinfo(host, None, socket.AF_INET)
        if results:
            ipv4 = results[0][4][0]
            logger.info(f"Resolved {host} → IPv4 {ipv4} (IPv6 bypassed)")
            return {"hostaddr": ipv4}
    except OSError as e:
        logger.warning(f"IPv4 resolution failed for {host}: {e}")
    return {}


Base = declarative_base()


class PostgreSQLDatabase(BaseDatabase):
    """PostgreSQL database implementation."""

    def __init__(self, config: PostgreSQLSettings):
        self.config = config
        self.engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker] = None

    def startup(self) -> None:
        """Initialize the database connection."""
        try:
            # Log connection attempt
            logger.info(
                f"Attempting to connect to PostgreSQL at: {self.config.database_url.split('@')[1] if '@' in self.config.database_url else 'localhost'}"
            )

            connect_args = {}
            url = self.config.database_url
            if "neon.tech" in url or "sslmode=require" in url:
                connect_args["sslmode"] = "require"
                # Force IPv4 — psycopg2 uses hostaddr for the TCP connection
                # and host for SSL SNI, so both IPv4 routing and SSL work correctly
                connect_args.update(_force_ipv4_connect_arg(url))

            self.engine = create_engine(
                url,
                echo=self.config.echo_sql,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_pre_ping=True,
                connect_args=connect_args,
            )

            self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

            # Test the connection
            assert self.engine is not None
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("Database connection test successful")

            # Check which tables exist before creating
            inspector = inspect(self.engine)
            existing_tables = inspector.get_table_names()

            # Create tables if they don't exist (idempotent operation)
            Base.metadata.create_all(bind=self.engine)

            # Check if any new tables were created
            updated_tables = inspector.get_table_names()
            new_tables = set(updated_tables) - set(existing_tables)

            if new_tables:
                logger.info(f"Created new tables: {', '.join(new_tables)}")
            else:
                logger.info("All tables already exist - no new tables created")

            logger.info("PostgreSQL database initialized successfully")
            assert self.engine is not None
            logger.info(f"Database: {self.engine.url.database}")
            logger.info(f"Total tables: {', '.join(updated_tables) if updated_tables else 'None'}")
            logger.info("Database connection established")

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise

    def teardown(self) -> None:
        """Close the database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("PostgreSQL database connections closed")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call startup() first.")

        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
