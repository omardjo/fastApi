import databases
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from blogapi.config import config


metadata = sqlalchemy.MetaData()

post_table = sqlalchemy.Table(
    "posts",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("body", sqlalchemy.String, nullable=False),
)

comment_table = sqlalchemy.Table(
    "comments",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("body", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("post_id", sqlalchemy.ForeignKey("posts.id"), nullable=False),
)

user_table = sqlalchemy.Table(
    "users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("email", sqlalchemy.String(255), nullable=False, unique=True),
    sqlalchemy.Column("password_hash", sqlalchemy.String, nullable=False),
    sqlalchemy.Column(
        "created_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
)

refresh_token_table = sqlalchemy.Table(
    "refresh_tokens",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column(
        "user_id", sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ),
    sqlalchemy.Column(
        "token_hash", sqlalchemy.String(128), nullable=False, unique=True
    ),
    sqlalchemy.Column("expires_at", sqlalchemy.DateTime(timezone=True), nullable=False),
    sqlalchemy.Column("revoked_at", sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.Column(
        "created_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
    sqlalchemy.Column(
        "replaced_by_token_id",
        sqlalchemy.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sqlalchemy.Column("ip_address", sqlalchemy.String(64), nullable=True),
    sqlalchemy.Column("user_agent", sqlalchemy.String(512), nullable=True),
    sqlalchemy.Column("device_id", sqlalchemy.String(128), nullable=True),
)

auth_security_event_table = sqlalchemy.Table(
    "auth_security_events",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column(
        "user_id", sqlalchemy.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    ),
    sqlalchemy.Column("event_type", sqlalchemy.String(64), nullable=False),
    sqlalchemy.Column("ip_address", sqlalchemy.String(64), nullable=True),
    sqlalchemy.Column("user_agent", sqlalchemy.String(512), nullable=True),
    sqlalchemy.Column("device_id", sqlalchemy.String(128), nullable=True),
    sqlalchemy.Column("token_id", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("details", sqlalchemy.JSON, nullable=True),
    sqlalchemy.Column(
        "created_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
)


def _async_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


engine = create_async_engine(_async_url(config.database_url))


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        # Compatibility migration for existing databases created before email auth.
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'users' AND column_name = 'username'
                    ) THEN
                        UPDATE users
                        SET email = username || '@legacy.local'
                        WHERE email IS NULL;
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(
            sqlalchemy.text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'users' AND column_name = 'username' AND is_nullable = 'NO'
                    ) THEN
                        ALTER TABLE users ALTER COLUMN username DROP NOT NULL;
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE users ALTER COLUMN email SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS user_agent VARCHAR(512)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS device_id VARCHAR(128)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                """
                CREATE TABLE IF NOT EXISTS auth_security_events (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                    event_type VARCHAR(64) NOT NULL,
                    ip_address VARCHAR(64) NULL,
                    user_agent VARCHAR(512) NULL,
                    device_id VARCHAR(128) NULL,
                    token_id INTEGER NULL,
                    details JSONB NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_auth_security_events_user_id ON auth_security_events (user_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_auth_security_events_event_type ON auth_security_events (event_type)"
            )
        )


database = databases.Database(
    config.database_url,
    force_rollback=config.db_force_rollback,
)
