"""Allows ``python -m jobs_radar.worker``."""

import asyncio

from jobs_radar.worker.main import main

if __name__ == "__main__":
    asyncio.run(main())
