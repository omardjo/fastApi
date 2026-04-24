from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from blogapi.config import config
from blogapi.db_diagnostics import run_db_diagnostics
from blogapi.security import get_current_user


router = APIRouter(tags=["health"], dependencies=[Depends(get_current_user)])


@router.get("/health/db")
async def health_db():
    report = await run_db_diagnostics(config.database_url)

    dns_ok = report.get("dns", {}).get("ok", False)
    tcp_ok = report.get("tcp", {}).get("ok", False)
    auth_plain_ok = report.get("auth_plain", {}).get("ok", False)
    auth_ssl_ok = report.get("auth_ssl_require", {}).get("ok", False)

    # Healthy if DNS + TCP work and at least one auth method works
    is_healthy = dns_ok and tcp_ok and (auth_plain_ok or auth_ssl_ok)

    report["status"] = "healthy" if is_healthy else "unhealthy"

    # Remove sensitive database URL from response
    report.pop("database_url", None)

    return JSONResponse(
        content=report,
        status_code=200 if is_healthy else 503,
    )
