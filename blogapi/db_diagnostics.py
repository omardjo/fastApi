import asyncio
import socket
import ssl
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import asyncpg


def redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    username = parsed.username or ""
    password = parsed.password
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""

    auth = ""
    if username:
        auth = username
        if password is not None:
            auth += ":***"
        auth += "@"

    netloc = f"{auth}{hostname}{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _normalize_asyncpg_url(database_url: str) -> str:
    parsed = urlparse(database_url)

    # asyncpg accepts postgresql://, not postgresql+asyncpg://
    scheme = "postgresql" if parsed.scheme.startswith("postgresql") else parsed.scheme

    query = parse_qs(parsed.query, keep_blank_values=True)

    # asyncpg does not understand ssl=require or sslmode=require inside the URL
    query.pop("ssl", None)
    query.pop("sslmode", None)

    encoded_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(scheme=scheme, query=encoded_query))


async def run_db_diagnostics(database_url: str, timeout: float = 5.0) -> dict[str, Any]:
    parsed = urlparse(database_url)
    host = parsed.hostname
    port = parsed.port or 5432
    db_name = parsed.path.lstrip("/") if parsed.path else ""

    report: dict[str, Any] = {
        "database_url": redact_database_url(database_url),
        "host": host,
        "port": port,
        "database": db_name,
        "dns": {"ok": False, "error": None},
        "tcp": {"ok": False, "error": None},
        "auth_plain": {"ok": False, "error": None},
        "auth_ssl_require": {"ok": False, "error": None},
        "status": "unhealthy",
    }

    if not host:
        report["dns"]["error"] = "No host found in DATABASE_URL"
        return report

    try:
        await asyncio.to_thread(socket.getaddrinfo, host, port)
        report["dns"]["ok"] = True
    except Exception as exc:
        report["dns"]["error"] = f"{type(exc).__name__}: {exc}"
        return report

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        report["tcp"]["ok"] = True
    except Exception as exc:
        report["tcp"]["error"] = f"{type(exc).__name__}: {exc}"
        return report

    clean_url = _normalize_asyncpg_url(database_url)

    # Plain connection test
    try:
        conn = await asyncpg.connect(clean_url, timeout=timeout)
        await conn.close()
        report["auth_plain"]["ok"] = True
        report["status"] = "healthy"
        return report
    except Exception as exc:
        report["auth_plain"]["error"] = f"{type(exc).__name__}: {exc}"

    # SSL connection test for AWS RDS
    try:
        ssl_context = ssl.create_default_context()
        conn = await asyncpg.connect(
            clean_url,
            timeout=timeout,
            ssl=ssl_context,
        )
        await conn.close()
        report["auth_ssl_require"]["ok"] = True
        report["status"] = "healthy_with_ssl"
        return report
    except Exception as exc:
        report["auth_ssl_require"]["error"] = f"{type(exc).__name__}: {exc}"

    return report
