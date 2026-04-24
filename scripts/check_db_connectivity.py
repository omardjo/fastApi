import asyncio
import json

from blogapi.config import config
from blogapi.db_diagnostics import run_db_diagnostics


async def main() -> None:
    report = await run_db_diagnostics(config.database_url)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
