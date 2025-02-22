# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# This file contains all handling to be done with the Harmony Link TTS Module
import logging

# Import Client base Module
from harmony_modules.common import *

import sounddevice as sd
import soundfile as sf

import random
import time
from threading import Thread

# Specify RNG lib here in case we need to replace it at some point
rng = random.Random()


class TTSProcessorThread(Thread):
    def __init__(self, tts_handler, lipsync_interval=0.1):
        # execute the base constructor
        Thread.__init__(self)
        # Control flow
        self.running = False
        # Params
        self.tts_handler = tts_handler
        self.lipsync_interval = lipsync_interval if lipsync_interval >= 0.1 else 0.1

    def run(self):
        self.running = True
        while self.running:
            if not self.wait_voice_played():
                time.sleep(self.lipsync_interval)
                continue
            self.running = False

    def wait_voice_played(self):
        if not self.tts_handler.playing_stream:
            logging.error('[{0}]: Tried to monitor an undefined playback stream!')
            return True

        if self.tts_handler.playing_stream.is_active():
            self.tts_handler.fake_lipsync_update()
            return False
        else:
            # here the sound file is played, you can mark some flag or delete the file
            logging.debug('[{0}]: Done playing file: {1}!'.format(self.tts_handler.__class__.__name__, self.tts_handler.playing_utterance['audio_file']))
            # Send Message to Harmony Link to delete the source file from disk
            playback_done_event = HarmonyLinkEvent(
                event_id='playback_done',  # This is an arbitrary dummy ID to conform the Harmony Link API
                event_type=EVENT_TYPE_TTS_PLAYBACK_DONE,
                status=EVENT_STATE_NEW,
                payload=self.tts_handler.playing_utterance['audio_file']
            )
            self.tts_handler.backend_connector.send_event(playback_done_event)
            self.tts_handler.playing_stream.close()
            self.tts_handler.fake_lipsync_stop()
            # Recursive call to PlayVoice in case we have pending audios for this AI Entity
            self.tts_handler.playing_stream = None
            self.tts_handler.playing_utterance = None
            self.tts_handler.play_voice()
            return True


# TextToSpeechHandler - main module class
class TextToSpeechHandler(HarmonyClientModuleBase):
    def __init__(self, entity_controller, tts_config):
        # execute the base constructor
        HarmonyClientModuleBase.__init__(self, entity_controller=entity_controller)
        # Set config
        self.config = tts_config
        # Setup Audio Device
        self.setup_speaker()
        # TTS Handling
        self.speech_suppressed = False
        self.playing_utterance = None
        self.playing_stream = None
        self.pending_utterances = []

    def setup_speaker(self):
        available_devices = sd.query_devices()
        logging.debug('setting up speaker / audio output device')
        logging.debug(f"available devices:\n {available_devices}")

        if len(available_devices) == 0:
            raise RuntimeError('No output devices found!')

        try:
            device_id = int(self.config['speaker_device_override'])
            if device_id < 0:
                # This searches for a device with text 'CABLE Input' in it's name, in case no override is specified
                for idx, device in enumerate(available_devices):
                    if 'CABLE Input' in device.name:
                        device_id = idx
                        break
                # If no cable input is found, just try to use random output
                if device_id < 0:
                    device_id = 0
                    logging.warning(f"No audio output device with ID 'CABLE Input' in it's name found!"
                                    f"Device '{available_devices[device_id].name}' was assigned automatically.'")

            # Setup Output device in lib
            sd.check_output_settings(device_id)
            sd.default.samplerate = 44100
            sd.default.device = device_id
        except sd.PortAudioError:
            logging.error("Invalid output device! Make sure you've launched VB-Cable.\n",
                  "Check that you've choosed the correct output_device in initialize method.\n",
                  "From the list below, select device that starts with 'CABLE Input' and set output_device to it's id in list.\n",
                  "If you still have this error try every device that starts with 'CABLE Input'. If it doesn't help please create GitHub issue.")
            raise

    def handle_event(
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
                    self.backend_connector.send_event(playback_done_event)
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
                self.play_voice()

            # TODO: Update chara to perform lipsync on play

        return

    def play_voice(self):
        if self.playing_utterance is not None:
            return

        if len(self.pending_utterances) > 0:
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
                    outdata[:end - start] = self.playing_utterance['audio_data'][start:end]
                    outdata[end - start:] = 0
                    raise sd.CallbackStop()
                else:
                    outdata[:] = self.playing_utterance['audio_data'][start:end]
                self.playing_utterance['index'] = end

            if self.playing_utterance['audio_data'].ndim > 1:
                channels = self.playing_utterance['audio_data'].shape[1]
            else:
                channels = 1

            self.playing_stream = sd.OutputStream(
                samplerate=self.playing_utterance['sample_rate'],
                channels=channels,
                callback=callback
            ).start()

            logging.debug('[{0}]: Playing audio file: {1}'.format(self.__class__.__name__, audio_file))
            TTSProcessorThread(tts_handler=self).start()

    def suppress_speech(self, suppress=False):
        # Update suppression mode
        # if not suppressed, just return
        self.speech_suppressed = suppress
        if not self.speech_suppressed:
            return

        if self.playing_utterance is None:
            return

        self.playing_utterance.Stop()
        self.playing_utterance.Cleanup()
        self.playing_utterance = None
        self.pending_utterances = []
        self.fake_lipsync_stop()

    def fake_lipsync_stop(self):
        if self.chara is not None:
            self.chara.actor.set_mouth_open(0)

    def fake_lipsync_update(self):
        if self.chara is not None:
            mo = rng.random()
            if mo > 0.7:
                self.chara.actor.set_mouth_open(1.0)
            else:
                self.chara.actor.set_mouth_open(mo)
