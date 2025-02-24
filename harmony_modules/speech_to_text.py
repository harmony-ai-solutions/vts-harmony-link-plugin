# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# This file contains all handling to be done with the Harmony Link STT Module
#
# Import Client base Module
import logging

from harmony_modules.common import *

import threading
import base64
import time
import sounddevice as sd

# Constants
RESULT_MODE_PROCESS = "process"
RESULT_MODE_RETURN = "return"


# SpeechToTextHandler - module main class
class SpeechToTextHandler(HarmonyClientModuleBase):
    def __init__(self, entity_controller, stt_config):
        # execute the base constructor
        HarmonyClientModuleBase.__init__(self, entity_controller=entity_controller)
        # Set config
        self.config = stt_config
        # Get Base vars from config
        self.channels = int(self.config['channels'])
        self.bit_depth = int(self.config['bit_depth'])
        self.sample_rate = int(self.config['sample_rate'])
        self.buffer_clip_duration = int(self.config['buffer_clip_duration'])
        self.record_stepping = int(self.config['record_stepping'])
        self.microphone_name = self.get_microphone()
        # Recording Handling
        self.is_recording_microphone = False
        self.active_recording_events = {}
        self.recording_buffer = None # bytearray
        self.recording_start_time = None # time.time
        self.dropped_buffer_bytes = 0
        self.lock = threading.Lock()
        self.audio_stream = None
        # Calculate bytes per second
        self.bytes_per_sample = self.bit_depth // 8
        self.bytes_per_second = self.sample_rate * self.channels * self.bytes_per_sample
        # Calculate maximum buffer size in bytes
        self.max_buffer_bytes = self.bytes_per_second * self.buffer_clip_duration

    def handle_event(
            self,
            event  # HarmonyLinkEvent
    ):
        # Audio processed and utterance received
        if event.event_type == EVENT_TYPE_STT_OUTPUT_TEXT and event.status == EVENT_STATE_DONE:

            utterance_data = event.payload

            if len(utterance_data["content"]) > 0:
                # Since this was an output created by the current entity, it needs to be distributed
                # to the other entities, which then "decide" if it's relevant to them in some way or not
                utterance_data["entity_id"] = self.entity_controller.entity_id
                event = HarmonyLinkEvent(
                    event_id='actor_{0}_VAD_utterance'.format(self.entity_controller.entity_id),
                    event_type=EVENT_TYPE_PERCEPTION_ACTOR_UTTERANCE,
                    status=EVENT_STATE_DONE,
                    payload=utterance_data
                )

                # FIXME: This is not very performant, will cause issues with many characters
                for entity_id, controller in self.entity_controller.game.scenedata.active_entities.items():
                    if entity_id == self.entity_controller.entity_id or controller.perceptionModule is None:
                        continue
                    controller.perceptionModule.handle_event(event)

        # User / Source entity starts talking
        if event.event_type == EVENT_TYPE_STT_SPEECH_STARTED and event.status == EVENT_STATE_DONE:
            # This event is intended to perform as an "interruption event" for LLM and TTS
            # on the listening entities.
            # FIXME: This is not very performant, will cause issues with many characters
            for entity_id, controller in self.entity_controller.game.scenedata.active_entities.items():
                if entity_id == self.entity_controller.entity_id or controller.perceptionModule is None:
                    continue
                #
                event.payload = {
                    "entity_id": self.entity_controller.entity_id
                }
                controller.perceptionModule.handle_event(event)

        # User / Source entity stops talking
        if event.event_type == EVENT_TYPE_STT_SPEECH_STOPPED and event.status == EVENT_STATE_DONE:
            # This event is intended to perform as an "interruption event" for LLM and TTS
            # on the listening entities.
            # FIXME: This is not very performant, will cause issues with many characters
            for entity_id, controller in self.entity_controller.game.scenedata.active_entities.items():
                if entity_id == self.entity_controller.entity_id or controller.perceptionModule is None:
                    continue
                #
                event.payload = {
                    "entity_id": self.entity_controller.entity_id
                }
                controller.perceptionModule.handle_event(event)

        # Received event to start recording Audio through the Game's utilities
        if event.event_type == EVENT_TYPE_STT_FETCH_MICROPHONE and event.status == EVENT_STATE_DONE:
            # This event triggers the recording of an audio clip using the default microphone.
            # Upon finishing the recording, it will send the recorded audio to Harmony Link for VAD & STT transcription
            recording_task = event.payload
            # Extract parameters from recording task
            start_byte = recording_task.get('start_byte', 0)
            bytes_count = recording_task.get('bytes_count', self.bytes_per_second * 5)  # Default to 5 seconds

            # Start a new thread to handle recording
            fetch_microphone_thread = threading.Thread(
                target=self.process_recording_request,
                args=(event.event_id, start_byte, bytes_count)
            )
            fetch_microphone_thread.start()

            # Store event to mark it as processing
            self.active_recording_events[event.event_id] = event

    def start_listen(self):
        if self.is_recording_microphone:
            return False

        # Start recording from microphone via sounddevice
        if not self.start_continuous_recording():
            return False

        # Send Event to Harmony Link to listen to the recorded Audio
        event = HarmonyLinkEvent(
            event_id='start_listen',  # This is an arbitrary dummy ID to conform the Harmony Link API
            event_type=EVENT_TYPE_STT_START_LISTEN,
            status=EVENT_STATE_NEW,
            payload={
                "auto_vad": bool(self.config['auto_vad']),
                "result_mode": RESULT_MODE_RETURN if bool(self.config['auto_vad']) else RESULT_MODE_PROCESS,
                "channels": self.channels,
                "bit_depth": self.bit_depth,
                "sample_rate": self.sample_rate
            }
        )
        success = self.backend_connector.send_event(event)
        if success:
            logging.info('Harmony Link: listening...')
            self.is_recording_microphone = True
            return True
        else:
            logging.error('Harmony Link: listen failed')
            # Stop recording
            return False

    def stop_listen(self):
        if not self.is_recording_microphone:
            return False

        # Send Event to Harmony Link to stop listening
        event = HarmonyLinkEvent(
            event_id='stop_listen',  # This is an arbitrary dummy ID to conform the Harmony Link API
            event_type=EVENT_TYPE_STT_STOP_LISTEN,
            status=EVENT_STATE_NEW,
            payload={}
        )
        success = self.backend_connector.send_event(event)
        if success:
            logging.info('Harmony Link: listening stopped. Processing speech...')

            # Stop recording to ongoing audio clip
            if not self.stop_continuous_recording():
                logging.error('failed to stop continous recording')
                return False

            self.is_recording_microphone = False
            return True
        else:
            logging.error('Harmony Link: stop listen failed.')
            return False

    def get_microphone(self):
        logging.debug('setting up microphone / audio input device')
        # Determine the microphone to use
        devices = sd.query_devices()
        input_devices = [device for device in devices if device['max_input_channels'] > 0]
        microphone_name = self.config['microphone']

        if len(input_devices) <= 0:
            logging.warning('No microphone available.')
            return None
        else:
            microphones = ""
            for idx, device in enumerate(input_devices):
                microphones += "{0} : {1}\n".format(idx, device['name'])
            logging.debug(f"Available microphones:\n{microphones}")

        if microphone_name == 'default':
            # Get the index of the default input device
            default_device_index = sd.default.device[0]
            # Retrieve the name of the default input device
            microphone_name = sd.query_devices(default_device_index)['name']
        else:
            matching_devices = [device for device in input_devices if microphone_name in device['name']]
            if matching_devices:
                microphone_name = matching_devices[0]['name']
            else:
                logging.warning('No microphone with provided name "{0}" available.'.format(microphone_name))
                return None

        return microphone_name

    def start_continuous_recording(self):
        # This starts a continuous microphone recording clip which will be used to fetch
        # audio samples for Harmony's STT transcription module from the microphone

        # Reset Buffer before starting recording
        self.recording_buffer = bytearray()
        self.dropped_buffer_bytes = 0

        logging.debug('Recording with microphone: "{0}"'.format(self.microphone_name))

        def audio_stream_callback(indata, frames, time_info, status):
            if status:
                logging.debug(f"recording callback status: {status}")
            audio_data = indata.tobytes()
            with self.lock:
                self.recording_buffer.extend(audio_data)
                # Remove oldest data if buffer exceeds max size
                buffer_length = len(self.recording_buffer)
                if buffer_length > self.max_buffer_bytes:
                    excess_bytes = buffer_length - self.max_buffer_bytes
                    del self.recording_buffer[:excess_bytes]
                    self.dropped_buffer_bytes += excess_bytes

        try:
            # Get correct dtype
            if self.bit_depth == 8:
                dtype = 'int8'
            elif self.bit_depth == 16:
                dtype = 'int16'
            elif self.bit_depth == 24:
                dtype = 'int24'  # Note: int24 might not be supported directly
            elif self.bit_depth == 32:
                dtype = 'int32'
            else:
                raise ValueError(f"Unsupported bit depth: {self.bit_depth}")

            # Create stream
            self.audio_stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=int(self.sample_rate * self.record_stepping / 1000),
                device=self.microphone_name,
                channels=self.channels,
                dtype=dtype,
                callback=audio_stream_callback
            )
            self.audio_stream.start()
            self.recording_start_time = time.time()
            logging.debug('Continuous recording started.')
            return True
        except Exception as e:
            logging.error('Failed to start continuous recording: {}'.format(e))
            return False

    def stop_continuous_recording(self):
        if self.audio_stream is None:
            return False

        # Wait until all recording events have completed
        timeout_counter = 0
        while len(self.active_recording_events) > 0:
            if timeout_counter % 10 == 0:
                logging.debug('Waiting for recording events to finish...')
            if timeout_counter < 100:
                timeout_counter += 1
                time.sleep(0.1)
            else:
                logging.warning('Recording events did not finish within timeout of 10 seconds')
                break  # Proceed to stop recording anyway

        try:
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None
            logging.debug('Continuous recording stopped.')
            return True
        except Exception as e:
            logging.error('Failed to stop recording: {}'.format(e))
            return False

    def get_buffer_fetch_indices(self, start_byte, end_byte):
        actual_start_byte = start_byte - self.dropped_buffer_bytes
        actual_end_byte = end_byte - self.dropped_buffer_bytes
        buffer_size = len(self.recording_buffer)
        return actual_start_byte, actual_end_byte, buffer_size

    def process_recording_request(self, event_id, start_byte, bytes_count):
        # Get end byte
        end_byte = start_byte + bytes_count
        # Determine if we need to wait
        with self.lock:
            actual_start_byte, actual_end_byte, buffer_size = self.get_buffer_fetch_indices(start_byte, end_byte)

        # If start index is after current buffer boundary
        while actual_start_byte > buffer_size:
            time_till_buffer_reached = (actual_start_byte - buffer_size) / self.bytes_per_second
            time.sleep(time_till_buffer_reached)
            # Determine again if we need to wait more
            with self.lock:
                actual_start_byte, actual_end_byte, buffer_size = self.get_buffer_fetch_indices(start_byte, end_byte)

        # If end index is after current buffer boundary
        while actual_end_byte > buffer_size:
            time_till_buffer_reached = (actual_end_byte - buffer_size) / self.bytes_per_second
            time.sleep(time_till_buffer_reached)
            # Determine again if we need to wait more
            with self.lock:
                actual_start_byte, actual_end_byte, buffer_size = self.get_buffer_fetch_indices(start_byte, end_byte)

        # Get bytes from buffer
        with self.lock:
            actual_start_byte, actual_end_byte, buffer_size = self.get_buffer_fetch_indices(start_byte, end_byte)

            # Log final indices
            logging.debug("Bytes count: {0}".format(bytes_count))
            logging.debug("Start byte (total / buffer): {0} / {1}".format(start_byte, start_byte - self.dropped_buffer_bytes))
            logging.debug("End byte (total / buffer): {0} / {1}".format(end_byte, end_byte - self.dropped_buffer_bytes))

            audio_bytes = self.recording_buffer[actual_start_byte:actual_end_byte]

        # DEBUG CODE
        # print "Length of audio_bytes:", len(audio_bytes)
        # print "First 20 bytes of audio_bytes:", audio_bytes[:20]

        # Encode to base64
        encoded_data = base64.b64encode(audio_bytes)

        # DEBUG CODE
        # print "Length of encoded_data:", len(encoded_data)
        # print "First 50 characters of encoded_data:", encoded_data[:50]

        # Send result event
        result_event = HarmonyLinkEvent(
            event_id=event_id,
            event_type=EVENT_TYPE_STT_FETCH_MICROPHONE_RESULT,
            status=EVENT_STATE_NEW,
            payload={
                'audio_bytes': encoded_data,
                'channels': self.channels,
                'bit_depth': self.bit_depth,
                'sample_rate': self.sample_rate,
            }
        )
        self.backend_connector.send_event(result_event)
        # Remove the event from the tracking
        del self.active_recording_events[event_id]

