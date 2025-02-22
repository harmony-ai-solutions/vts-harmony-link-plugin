# Harmony Link Plugin for VNGE
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# User Controls Module

# Import Backend base Module
from harmony_modules.common import *

from pynput import keyboard

# ControlsHandler - module main class
class ControlsHandler(HarmonyClientModuleBase):
    def __init__(self, entity_controller, shutdown_func, controls_keymap_config):
        # execute the base constructor
        HarmonyClientModuleBase.__init__(self, entity_controller=entity_controller)
        # Set config
        self.keymap_config = controls_keymap_config
        # Game Object reference
        self.shutdown_func = shutdown_func
        # Module References
        self.entity_controller = entity_controller
        # Keyboard handling
        self.is_key_pressed = False
        self.listener = None

    def handle_event(
            self,
            event  # HarmonyLinkEvent
    ):
        # Not implemented
        return

    def activate(self):
        # Setup Keyboard listener
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()


    def deactivate(self):
        # Stop recording if active
        if self.entity_controller.sttModule and self.entity_controller.sttModule.is_recording_microphone:
            self.toggle_record_microphone()

        # Stop the keyboard listener
        if self.listener:
            self.listener.stop()
            self.listener = None

        # Disable base controller
        HarmonyClientModuleBase.deactivate(self)

    def toggle_record_microphone(self):
        if not self.entity_controller.sttModule:
            return

        if self.entity_controller.sttModule.is_recording_microphone:
            recording_aborted = self.entity_controller.sttModule.stop_listen()
            if not recording_aborted:
                logging.error('Harmony Link Plugin for VNGE: Failed to record from microphone.')
                return

        else:
            recording_started = self.entity_controller.sttModule.start_listen()
            if not recording_started:
                logging.error('Harmony Link Plugin for VNGE: Failed to record from microphone.')
                return

    def on_press(self, key):
        try:
            if key.char.upper() == self.keymap_config["toggle_microphone"].upper():
                if not self.is_key_pressed:
                    self.is_key_pressed = True
                    self.toggle_record_microphone()
        except AttributeError:
            pass  # Handle special keys that do not have 'char' attribute

    def on_release(self, key):
        try:
            if key.char.upper() == self.keymap_config["toggle_microphone"].upper():
                self.is_key_pressed = False
        except AttributeError:
            pass