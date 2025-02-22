import asyncio
import logging
import sys
import time

from harmony import start_harmony_ai
from waifu import Waifu

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
    start_harmony_ai()

    # waifu = Waifu()
    #
    # waifu.initialize(user_input_service='whisper',
    #                  stt_duration = None,
    #                  mic_index = None,
    #
    #                 chatbot_service='openai',
    #                 chatbot_model = None,
    #                 chatbot_temperature = None,
    #                 personality_file = None,
    #
    #                 tts_service='elevenlabs',
    #                 output_device=8,
    #                 tts_voice='Rebecca - wide emotional range',
    #                 tts_model = None
    #                 )
    #
    # while True:
    #     waifu.conversation_cycle()

if __name__ == "__main__":
    asyncio.run(main())