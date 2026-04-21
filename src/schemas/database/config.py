from pydantic import Field
from pydantic_settings import BaseSettings


class PostgreSQLSettings(BaseSettings):
    """PostgreSQL configuration settings."""

    database_url: str = Field(
        default="postgresql://rag_user:rag_password@localhost:5432/rag_db", description="PostgreSQL database URL"
    )
    echo_sql: bool = Field(default=False, description="Enable SQL query logging")
    pool_size: int = Field(default=20, description="Database connection pool size")
    max_overflow: int = Field(default=0, description="Maximum pool overflow")

    class Config:
        env_prefix = "POSTGRES_"
