# Harmony Link Plugin for VNGE
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# User Controls Module

# Import Backend base Module
from harmony_modules.common import *

import asyncio
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
        # Event loop reference for synchronizing threads
        self.loop = asyncio.get_event_loop()

    async def handle_event(
            self,
            event  # HarmonyLinkEvent
    ):
        # Not implemented
        return

    def activate(self):
        # Setup Keyboard listener
        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()


    def deactivate(self):
        # Stop recording if active
        if self.entity_controller.sttModule and self.entity_controller.sttModule.is_recording_microphone:
            # Use run_coroutine_threadsafe to submit coroutine to the event loop
            asyncio.run_coroutine_threadsafe(
                self.toggle_record_microphone(),
                self.loop
            )

        # Stop the keyboard listener
        if self.listener:
            self.listener.stop()
            self.listener = None

        # Disable base controller
        HarmonyClientModuleBase.deactivate(self)

    async def toggle_record_microphone(self):
        if not self.entity_controller.sttModule:
            return

        if self.entity_controller.sttModule.is_recording_microphone:
            recording_aborted = await self.entity_controller.sttModule.stop_listen()
            if not recording_aborted:
                logging.error('Harmony Link Plugin for VNGE: Failed to record from microphone.')
                return

        else:
            recording_started = await self.entity_controller.sttModule.start_listen()
            if not recording_started:
                logging.error('Harmony Link Plugin for VNGE: Failed to record from microphone.')
                return

    def on_press(self, key):
        try:
            if key.char.upper() == self.keymap_config["toggle_microphone"].upper():
                if not self.is_key_pressed:
                    self.is_key_pressed = True
                    # Use run_coroutine_threadsafe to submit coroutine to the event loop
                    asyncio.run_coroutine_threadsafe(
                        self.toggle_record_microphone(),
                        self.loop
                    )
        except AttributeError:
            pass  # Handle special keys that do not have 'char' attribute

    def on_release(self, key):
        try:
            if key.char.upper() == self.keymap_config["toggle_microphone"].upper():
                self.is_key_pressed = False
        except AttributeError:
            pass