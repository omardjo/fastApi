# Android Auth API Contract

This document defines exact request and response contracts for Android Jetpack Compose clients.

## Base Headers

- Content-Type: application/json
- Optional metadata headers for auth endpoints:
  - x-device-id: stable app/device identifier (recommended)
  - user-agent: mobile app user agent string (recommended)

## 1) Login

Endpoint:
- POST /auth/login

Request JSON:
```json
{
  "email": "user@example.com",
  "password": "secret123"
}
```

Success (200):
```json
{
  "access_token": "<opaque-or-jwt-like-token>",
  "refresh_token": "<opaque-refresh-token>",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": 123,
    "email": "user@example.com"
  }
}
```

Errors:
- 401 Invalid credentials
- 429 Too many requests

## 2) Refresh

Endpoint:
- POST /auth/refresh

Request JSON:
```json
{
  "refresh_token": "<current-refresh-token>"
}
```

Success (200):
```json
{
  "access_token": "<new-access-token>",
  "refresh_token": "<new-refresh-token>",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": 123,
    "email": "user@example.com"
  }
}
```

Errors:
- 401 Invalid refresh token
- 401 Refresh token has been revoked
- 401 Refresh token expired
- 429 Too many requests

Rotation rules:
- Every successful refresh invalidates the previous refresh token.
- Reuse of a revoked refresh token is treated as suspicious and logged in auth_security_events.

## 3) Logout (single session)

Endpoint:
- POST /auth/logout

Request JSON:
```json
{
  "refresh_token": "<current-refresh-token>"
}
```

Success:
- 204 No Content

Notes:
- Endpoint is idempotent. Already-revoked or unknown refresh tokens still return 204.

## 4) Logout All Sessions

Endpoint:
- POST /auth/logout-all

Headers:
- Authorization: Bearer <access_token>

Request body:
- empty

Success:
- 204 No Content

Notes:
- Revokes all active refresh tokens for the authenticated user.

## Android Client Flow

1. Login and keep access_token + refresh_token in memory only.
2. Call protected APIs with Authorization: Bearer <access_token>.
3. On 401 due to token expiry, call /auth/refresh with current refresh_token.
4. Replace both tokens with the returned pair.
5. On app logout, call /auth/logout with the current refresh_token.
6. For security reset from account settings, call /auth/logout-all.
