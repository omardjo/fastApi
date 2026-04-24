-- Auth + refresh token rotation migration (idempotent)
-- Run on PostgreSQL.

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

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

ALTER TABLE users ALTER COLUMN email SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replaced_by_token_id INTEGER NULL REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    ip_address VARCHAR(64) NULL,
    user_agent VARCHAR(512) NULL,
    device_id VARCHAR(128) NULL
);

ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64);
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS user_agent VARCHAR(512);
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS device_id VARCHAR(128);

CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_expires_at ON refresh_tokens (expires_at);

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
);

CREATE INDEX IF NOT EXISTS ix_auth_security_events_user_id ON auth_security_events (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_security_events_event_type ON auth_security_events (event_type);

COMMIT;
