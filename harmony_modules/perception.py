# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# Perception Module - Handles Outcome of Events being "recognized" by the AI Entity

# Import Backend base Module
from harmony_modules.common import *


# PerceptionHandler - module main class
class PerceptionHandler(HarmonyClientModuleBase):
    def __init__(self, entity_controller, perception_config):
        # execute the base constructor
        HarmonyClientModuleBase.__init__(self, entity_controller=entity_controller)
        # Set config
        self.config = perception_config

    def handle_event(
            self,
            event  # HarmonyLinkEvent
    ):

        # Suppress Speech output for the current entity
        if event.event_type == EVENT_TYPE_STT_SPEECH_STARTED and event.status == EVENT_STATE_DONE:
            # event_entity_id = event.payload
            self.entity_controller.ttsModule.suppress_speech(suppress=True)

        # Unsuppress Speech output for the current entity
        if event.event_type == EVENT_TYPE_STT_SPEECH_STOPPED and event.status == EVENT_STATE_DONE:
            # event_entity_id = event.payload
            self.entity_controller.ttsModule.suppress_speech(suppress=False)

        return




