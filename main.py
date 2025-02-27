import asyncio
import logging
import sys
import time

from harmony import start_harmony_ai

async def main() -> None:
    # Setup logging
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S %z'
    )

    # Init Harmony Link Plugin
    await start_harmony_ai()

    # Continuous event loop so the application won't shut down
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
