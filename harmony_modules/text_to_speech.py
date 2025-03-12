# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# This file contains all handling to be done with the Harmony Link TTS Module
import logging

# Import Client base Module
from harmony_modules.common import *

import sounddevice as sd
import soundfile as sf

import asyncio
import random

# Specify RNG lib here in case we need to replace it at some point
rng = random.Random()

# TextToSpeechHandler - main module class
class TextToSpeechHandler(HarmonyClientModuleBase):
    def __init__(self, entity_controller, tts_config):
        # execute the base constructor
        HarmonyClientModuleBase.__init__(self, entity_controller=entity_controller)
        # Set config
        self.config = tts_config
        # Setup Audio Device
        self.setup_speaker()
        # Event loop reference for synchronizing threads
        self.loop = asyncio.get_event_loop()
        # TTS Handling
        self.speech_suppressed = False
        self.playing_utterance = None
        self.playing_stream = None
        self.pending_utterances = []
        self.lipsync_interval = 0.1

    def setup_speaker(self):
        logging.debug('setting up speaker / audio output device')
        # Determine speaker to use
        available_devices = sd.query_devices()
        output_devices = [device for device in available_devices if device['max_output_channels'] > 0]
        speaker_name = self.config['speaker']
        speaker_index = None

        if len(output_devices) == 0:
            raise RuntimeError('No output devices found!')

        # Log available output devices
        devices_str = ""
        for idx, device in enumerate(output_devices):
            devices_str += f"{idx}: {device['name']}\n"
        logging.debug(f"Available output devices:\n{devices_str}")

        try:
            if speaker_name == 'default':
                # Get the index of the default output device
                default_output_index = sd.default.device[1]  # Output device is at index 1
                if default_output_index is None:
                    logging.error('No default output device found.')
                    raise RuntimeError('No default output device found.')
                speaker_index = default_output_index
                speaker_name = sd.query_devices(default_output_index)['name']
            else:
                matching_devices = [device for device in output_devices if speaker_name in device['name']]
                if matching_devices:
                    speaker_index = matching_devices[0]['index']
                    speaker_name = matching_devices[0]['name']
                else:
                    logging.warning(f'No speaker with name containing "{speaker_name}" found.')
                    raise RuntimeError(f'No speaker with name containing "{speaker_name}" found.')

            # Setup Output device in lib
            sd.check_output_settings(device=speaker_index)
            sd.default.samplerate = 44100
            sd.default.device = (sd.default.device[0], speaker_index)
            logging.debug(f'Speaker set to "{speaker_name}" with index {speaker_index}.')
        except Exception as e:
            logging.error(f"Failed to set up speaker: {e}")
            raise

    async def handle_event(
            self,
            event  # HarmonyLinkEvent
    ):
        # AI Status update
        if event.event_type == EVENT_TYPE_AI_STATUS and event.status == EVENT_STATE_DONE:
            self.update_ai_state(ai_state=event.payload)

        # AI Speech Utterance
        if (
                event.event_type == EVENT_TYPE_AI_SPEECH or
                event.event_type == EVENT_TYPE_AI_ACTION
        ) and event.status == EVENT_STATE_DONE:

            utterance_data = event.payload
            audio_file = utterance_data["audio_file"]

            if len(audio_file) > 0:
                # Just abort here if speech is suppressed for this actor
                if self.speech_suppressed:
                    logging.debug('Speech currently suppressed. Ignoring utterance'.format())
                    # Send Message to Harmony Link to delete the source file from disk
                    playback_done_event = HarmonyLinkEvent(
                        event_id='playback_done',  # This is an arbitrary dummy ID to conform the Harmony Link API
                        event_type=EVENT_TYPE_TTS_PLAYBACK_DONE,
                        status=EVENT_STATE_NEW,
                        payload=audio_file
                    )
                    await self.backend_connector.send_event(playback_done_event)
                    return

                # Build Sound source and queue it for playing
                # soundType can be "BGM", "ENV", "SystemSE" or "GameSE"
                # they are almost the same but with separated volume control in studio setting
                audio_data, sample_rate = sf.read(audio_file)
                logging.debug('[{0}]: Successfully loaded audio file: {1}'.format(self.__class__.__name__, audio_file))

                # Append to queue
                self.pending_utterances.append((
                    audio_file,
                    audio_data,
                    sample_rate
                ))
                # Play
                await self.play_voice()

            # TODO: Update chara to perform lipsync on play

        return

    async def play_voice(self):
        if self.playing_utterance is not None:
            return

        while len(self.pending_utterances) > 0:
            audio_file, audio_data, sample_rate = self.pending_utterances.pop(0)

            # Keep reference to the currently playing utterance
            self.playing_utterance = {
                'audio_file': audio_file,
                'audio_data': audio_data,
                'sample_rate': sample_rate,
                'index': 0,
                'length': len(audio_data)
            }

            def callback(outdata, frames, time, status):
                start = self.playing_utterance['index']
                end = start + frames
                if end > self.playing_utterance['length']:
                    end = self.playing_utterance['length']

                data_slice = self.playing_utterance['audio_data'][start:end]
                # Reshape array in case audio data is mono
                if data_slice.ndim == 1:
                    data_slice = data_slice[:, None]

                out_frames = len(data_slice)
                outdata[:out_frames] = data_slice

                if out_frames < frames:
                    outdata[out_frames:] = 0
                    self.loop.call_soon_threadsafe(self.playback_finished)
                    raise sd.CallbackStop()

                self.playing_utterance['index'] = end

            # Determine if Stereo or Mono Audio
            channels = self.playing_utterance['audio_data'].shape[1] if self.playing_utterance['audio_data'].ndim > 1 else 1

            # Play audio
            self.playing_stream = sd.OutputStream(
                samplerate=self.playing_utterance['sample_rate'],
                channels=channels,
                callback=callback
            )
            self.playing_stream.start()
            logging.debug(f'[TextToSpeechHandler]: Playing audio file: {audio_file}')
            # Wait until audio stream has been played completely or surpressed
            await self.monitor_playback()

    async def monitor_playback(self):
        while self.playing_stream and self.playing_stream.active:
            asyncio.run_coroutine_threadsafe(self.fake_lipsync_update(), self.loop)
            await asyncio.sleep(self.lipsync_interval)

    def playback_finished(self):
        logging.debug(f'[TextToSpeechHandler]: Done playing file: {self.playing_utterance["audio_file"]}')

        # Send Playback done event to harmony link, so the audio file gets cleaned up.
        playback_done_event = HarmonyLinkEvent(
            event_id='playback_done',
            event_type=EVENT_TYPE_TTS_PLAYBACK_DONE,
            status=EVENT_STATE_NEW,
            payload=self.playing_utterance['audio_file']
        )
        asyncio.create_task(self.backend_connector.send_event(playback_done_event))

        # Cleanup
        self.playing_stream.close()
        asyncio.run_coroutine_threadsafe(self.fake_lipsync_stop(), self.loop)
        self.playing_stream = None
        self.playing_utterance = None

    def suppress_speech(self, suppress=False):
        # Update suppression mode
        # if not suppressed, just return
        self.speech_suppressed = suppress
        if not self.speech_suppressed:
            return

        if self.playing_stream is None:
            return

        # Stop the stream and cleanup
        self.playing_stream.close()
        asyncio.run_coroutine_threadsafe(self.fake_lipsync_stop(), self.loop)
        self.playing_stream = None
        self.playing_utterance = None
        self.pending_utterances = []

    async def fake_lipsync_stop(self):
        # logging.debug("[TextToSpeechHandler]: Fake Lipsync stopping")
        if self.chara is not None:
            await self.chara.controller.set_mouth_open(0)

    async def fake_lipsync_update(self):
        # logging.debug("[TextToSpeechHandler]: Fake Lipsync updating")
        if self.chara is not None:
            mo = rng.random()
            if mo > 0.7:
                await self.chara.controller.set_mouth_open(1.0)
            else:
                await self.chara.controller.set_mouth_open(mo)
