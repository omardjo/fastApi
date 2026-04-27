import databases
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from blogapi.config import config

metadata = sqlalchemy.MetaData()

post_table = sqlalchemy.Table(
    "posts",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("body", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("title", sqlalchemy.String(255), nullable=False),
    sqlalchemy.Column("slug", sqlalchemy.String(255), nullable=False, unique=True),
    sqlalchemy.Column("content", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("cover_image_url", sqlalchemy.String(1024), nullable=True),
    sqlalchemy.Column("thumbnail_url", sqlalchemy.String(1024), nullable=True),
    sqlalchemy.Column("excerpt", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column(
        "status", sqlalchemy.String(32), nullable=False, server_default="draft"
    ),
    sqlalchemy.Column(
        "created_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
    sqlalchemy.Column(
        "updated_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
    sqlalchemy.Column(
        "author_id",
        sqlalchemy.ForeignKey("users.id"),
        nullable=False,
    ),
    sqlalchemy.Column(
        "category_id",
        sqlalchemy.ForeignKey("categories.id"),
        nullable=False,
    ),
)

comment_table = sqlalchemy.Table(
    "comments",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("body", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column(
        "created_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
    sqlalchemy.Column(
        "post_id", sqlalchemy.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    ),
    sqlalchemy.Column(
        "author_id",
        sqlalchemy.ForeignKey("users.id"),
        nullable=False,
    ),
)

user_table = sqlalchemy.Table(
    "users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("username", sqlalchemy.String(150), nullable=False, unique=True),
    sqlalchemy.Column("email", sqlalchemy.String(255), nullable=False, unique=True),
    sqlalchemy.Column("password_hash", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("display_name", sqlalchemy.String(150), nullable=True),
    sqlalchemy.Column("bio", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("avatar_url", sqlalchemy.String(1024), nullable=True),
    sqlalchemy.Column(
        "role", sqlalchemy.String(50), nullable=False, server_default="user"
    ),
    sqlalchemy.Column(
        "created_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
)

category_table = sqlalchemy.Table(
    "categories",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.String(120), nullable=False, unique=True),
    sqlalchemy.Column("slug", sqlalchemy.String(140), nullable=False, unique=True),
)

tag_table = sqlalchemy.Table(
    "tags",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.String(80), nullable=False, unique=True),
)

post_tag_table = sqlalchemy.Table(
    "post_tags",
    metadata,
    sqlalchemy.Column(
        "post_id",
        sqlalchemy.ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "tag_id", sqlalchemy.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    ),
)

saved_post_table = sqlalchemy.Table(
    "saved_posts",
    metadata,
    sqlalchemy.Column(
        "user_id",
        sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "post_id",
        sqlalchemy.ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "created_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
)

reading_record_table = sqlalchemy.Table(
    "reading_records",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column(
        "user_id", sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ),
    sqlalchemy.Column(
        "post_id", sqlalchemy.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    ),
    sqlalchemy.Column(
        "progress_percent", sqlalchemy.Integer, nullable=False, server_default="0"
    ),
    sqlalchemy.Column(
        "reading_minutes", sqlalchemy.Integer, nullable=False, server_default="0"
    ),
    sqlalchemy.Column(
        "completed_at", sqlalchemy.DateTime(timezone=True), nullable=True
    ),
    sqlalchemy.Column(
        "updated_at",
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
)

user_settings_table = sqlalchemy.Table(
    "user_settings",
    metadata,
    sqlalchemy.Column(
        "user_id",
        sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "notifications_enabled",
        sqlalchemy.Boolean,
        nullable=False,
        server_default="true",
    ),
    sqlalchemy.Column(
        "appearance", sqlalchemy.String(32), nullable=False, server_default="system"
    ),
    sqlalchemy.Column(
        "language", sqlalchemy.String(16), nullable=False, server_default="en"
    ),
    sqlalchemy.Column(
        "updated_at",
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
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(150)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'user'"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(150)"
            )
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT")
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(1024)"
            )
        )
        await conn.execute(sqlalchemy.text("""
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
                """))
        await conn.execute(
            sqlalchemy.text("ALTER TABLE users ALTER COLUMN email SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text(
                "UPDATE users SET created_at = NOW() WHERE created_at IS NULL"
            )
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE users ALTER COLUMN created_at SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("UPDATE users SET role = 'user' WHERE role IS NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE users ALTER COLUMN role SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text(
                "UPDATE users SET username = regexp_replace(split_part(email, '@', 1), '[^a-zA-Z0-9_]+', '_', 'g') || '_' || id WHERE username IS NULL"
            )
        )
        await conn.execute(sqlalchemy.text("""
                INSERT INTO users (username, email, password_hash, role, created_at)
                SELECT 'system_user', 'system@internal.local', 'disabled:disabled', 'system', NOW()
                WHERE NOT EXISTS (SELECT 1 FROM users)
                """))
        await conn.execute(
            sqlalchemy.text("ALTER TABLE users ALTER COLUMN username SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS title VARCHAR(255)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS slug VARCHAR(255)"
            )
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS content TEXT")
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS cover_image_url VARCHAR(1024)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS thumbnail_url VARCHAR(1024)"
            )
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS excerpt TEXT")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN body TYPE TEXT")
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS status VARCHAR(32) DEFAULT 'draft'"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS author_id INTEGER"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS category_id INTEGER"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments ADD COLUMN IF NOT EXISTS author_id INTEGER"
            )
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE comments ALTER COLUMN body TYPE TEXT")
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE TABLE IF NOT EXISTS categories (id SERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL UNIQUE, slug VARCHAR(140) NOT NULL UNIQUE)"
            )
        )
        await conn.execute(sqlalchemy.text("""
                INSERT INTO categories (name, slug)
                VALUES ('Uncategorized', 'uncategorized')
                ON CONFLICT (slug) DO NOTHING
                """))
        await conn.execute(
            sqlalchemy.text(
                "CREATE TABLE IF NOT EXISTS tags (id SERIAL PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE TABLE IF NOT EXISTS post_tags (post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE, tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE, PRIMARY KEY (post_id, tag_id))"
            )
        )
        await conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS saved_posts (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, post_id)
                )
                """))
        await conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS reading_records (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    reading_minutes INTEGER NOT NULL DEFAULT 0,
                    completed_at TIMESTAMPTZ NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """))
        await conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    appearance VARCHAR(32) NOT NULL DEFAULT 'system',
                    language VARCHAR(16) NOT NULL DEFAULT 'en',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """))
        await conn.execute(
            sqlalchemy.text(
                "UPDATE posts SET title = left(body, 255), content = body WHERE title IS NULL OR content IS NULL"
            )
        )
        await conn.execute(
            sqlalchemy.text("UPDATE posts SET status = 'draft' WHERE status IS NULL")
        )
        await conn.execute(
            sqlalchemy.text(
                "UPDATE posts SET created_at = NOW() WHERE created_at IS NULL"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "UPDATE posts SET updated_at = COALESCE(updated_at, created_at, NOW())"
            )
        )
        await conn.execute(
            sqlalchemy.text("UPDATE posts SET slug = 'post-' || id WHERE slug IS NULL")
        )
        await conn.execute(sqlalchemy.text("""
                UPDATE posts
                SET author_id = (SELECT id FROM users ORDER BY id LIMIT 1)
                WHERE author_id IS NULL
                   OR NOT EXISTS (SELECT 1 FROM users WHERE users.id = posts.author_id)
                """))
        await conn.execute(sqlalchemy.text("""
                UPDATE posts
                SET category_id = (SELECT id FROM categories WHERE slug = 'uncategorized')
                WHERE category_id IS NULL
                   OR NOT EXISTS (
                       SELECT 1 FROM categories WHERE categories.id = posts.category_id
                   )
                """))
        await conn.execute(sqlalchemy.text("""
                UPDATE comments
                SET author_id = (SELECT author_id FROM posts WHERE posts.id = comments.post_id)
                WHERE author_id IS NULL
                   OR NOT EXISTS (SELECT 1 FROM users WHERE users.id = comments.author_id)
                """))
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN title SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN slug SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN content SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN status SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN created_at SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN updated_at SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN author_id SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE posts ALTER COLUMN category_id SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE comments ALTER COLUMN author_id SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text(
                "UPDATE comments SET created_at = NOW() WHERE created_at IS NULL"
            )
        )
        await conn.execute(
            sqlalchemy.text("ALTER TABLE comments ALTER COLUMN created_at SET NOT NULL")
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts DROP CONSTRAINT IF EXISTS fk_posts_author_id_users"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_author_id_fkey"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD CONSTRAINT fk_posts_author_id_users FOREIGN KEY (author_id) REFERENCES users(id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts DROP CONSTRAINT IF EXISTS fk_posts_category_id_categories"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_category_id_fkey"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE posts ADD CONSTRAINT fk_posts_category_id_categories FOREIGN KEY (category_id) REFERENCES categories(id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments DROP CONSTRAINT IF EXISTS fk_comments_post_id_posts"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments DROP CONSTRAINT IF EXISTS comments_post_id_fkey"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments ADD CONSTRAINT fk_comments_post_id_posts FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments DROP CONSTRAINT IF EXISTS fk_comments_author_id_users"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments DROP CONSTRAINT IF EXISTS comments_author_id_fkey"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE comments ADD CONSTRAINT fk_comments_author_id_users FOREIGN KEY (author_id) REFERENCES users(id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE post_tags DROP CONSTRAINT IF EXISTS post_tags_post_id_fkey"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE post_tags ADD CONSTRAINT post_tags_post_id_fkey FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE post_tags DROP CONSTRAINT IF EXISTS post_tags_tag_id_fkey"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE post_tags ADD CONSTRAINT post_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_posts_slug ON posts (slug)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_posts_author_id ON posts (author_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_posts_category_id ON posts (category_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_posts_status ON posts (status)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_comments_post_id ON comments (post_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_comments_author_id ON comments (author_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_post_tags_tag_id ON post_tags (tag_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_saved_posts_post_id ON saved_posts (post_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_reading_records_user_post ON reading_records (user_id, post_id)"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_reading_records_post_id ON reading_records (post_id)"
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
        await conn.execute(sqlalchemy.text("""
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
                """))
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
