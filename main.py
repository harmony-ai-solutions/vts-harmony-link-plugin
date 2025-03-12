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
    launch_success = await start_harmony_ai()
    if not launch_success:
        logging.info('Harmony Plugin failed to start. Shutting down.')
        return
    logging.info('Harmony Plugin started successfully. You can Toggle Speech Processing via Microphone now.')

    # Continuous event loop so the application won't shut down
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logging.info('Main coroutine cancelled, shutting down')


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('Program interrupted by user')
