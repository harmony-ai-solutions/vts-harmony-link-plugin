# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# This plugin is a derived version of our VNGE Plugin, modified to work with VTube Studio.
#
# For more Info on the project goals, see README.md
#
import asyncio
import configparser
import logging
import os
import threading
import time

import harmony_globals
from VTSController import VTSController
from harmony_modules import connector, common, text_to_speech, speech_to_text, \
    perception, controls  # , backend, countenance, movement
from harmony_modules.common import EVENT_TYPE_INIT_ENTITY

# Config
_config = None

_syncLock = threading.Lock()


# EntityInitHandler
class EntityInitHandler(common.HarmonyClientModuleBase):
    global _syncLock

    def __init__(self, entity_controller, entity_id):
        # execute the base constructor
        common.HarmonyClientModuleBase.__init__(self, entity_controller=entity_controller)
        # Set config
        self.entity_id = entity_id

    def handle_event(
            self,
            event  # HarmonyLinkEvent
    ):
        # Wait for Events required for initialization
        if event.event_type == EVENT_TYPE_INIT_ENTITY:
            # Acquire lock to avoid concurrency issues
            _syncLock.acquire()
            if event.status == common.EVENT_STATE_DONE:
                harmony_globals.ready_entities.append(self.entity_id)
            else:
                harmony_globals.failed_entities.append(self.entity_id)

            # Check for init done condition
            self.check_init_done()
            # Release lock
            _syncLock.release()
            # Disable this handler, it is not needed anymore after init
            self.deactivate()

    def check_init_done(self):
        logging.debug("Ready entities: {}".format(len(harmony_globals.ready_entities)))
        logging.debug("Failed entities: {}".format(len(harmony_globals.failed_entities)))
        logging.debug("Active entities: {}".format(len(harmony_globals.active_entities)))

        if len(harmony_globals.ready_entities) + len(harmony_globals.failed_entities) == len(harmony_globals.active_entities):
            if len(harmony_globals.failed_entities) == 0:
                # Entity Initialization done - start VTS routines
                asyncio.create_task(post_init())
            else:
                _error_abort('Harmony Link: Entity Initialization failed.')


# Chara - Internal representation for a chara actor
class Chara:
    def __init__(self, controller : VTSController):
        self.controller = controller


class EntityController:

    def __init__(self, entity_id, config):
        # Flow Control
        self.is_active = False
        # Important reference
        self.entity_id = entity_id
        self.config = config
        self.chara = None
        # Mandatory Modules
        self.initHandler = None
        self.connector = None
        # Feature Modules
        self.backendModule = None
        self.countenanceModule = None
        self.ttsModule = None
        self.sttModule = None
        self.movementModule = None
        self.perceptionModule = None
        self.controlsModule = None

    def activate(self):
        if self.is_active:
            return

        # Set active
        logging.debug('Starting EntityController for entity \'{0}\'...'.format(self.entity_id))
        self.is_active = True

        # Initialize Character on Harmony Link
        init_event = common.HarmonyLinkEvent(
            event_id='init_entity',  # This is an arbitrary dummy ID to conform the Harmony Link API
            event_type=EVENT_TYPE_INIT_ENTITY,
            status=common.EVENT_STATE_NEW,
            payload={
                'entity_id': self.entity_id
            }
        )
        init_send_success = self.connector.send_event(init_event)
        if init_send_success:
            logging.debug('Harmony Link: Initializing entity \'{0}\'...'.format(self.entity_id))
        else:
            raise RuntimeError('Harmony Link: Failed to sent entity initialize Event for entity \'{0}\'.'.format(self.entity_id))

    def is_active(self):
        return self.is_active

    # _init_modules initializes all the interfaces and handlers needed by harmony_modules
    def init_modules(self):

        # Init comms module for interfacing with external helper binaries
        self.connector = connector.ConnectorEventHandler(
            ws_endpoint=self.config.get('Connector', 'ws_endpoint'),
            shutdown_func=shutdown,  # -> A hard error with a single entity should cause the whole plugin to shut down.
        )
        self.connector.start()

        # Init Backend Module
        # self.backendModule = backend.BackendHandler(
        #     entity_controller=self,
        #     backend_config=dict(self.config.items('Backend'))
        # )
        # self.backendModule.activate()

        # Init Module for Audio Recording / Streaming + Player Speech-To-Text
        self.sttModule = speech_to_text.SpeechToTextHandler(
            entity_controller=self,
            stt_config=dict(self.config.items('STT'))
        )

        # Init Module for AI Expression Handling
        # self.countenanceModule = countenance.CountenanceHandler(
        #     entity_controller=self,
        #     countenance_config=dict(self.config.items('Countenance'))
        # )
        # self.countenanceModule.activate()

        # Init Module for AI Voice Streaming + Audio-2-LipSync
        self.ttsModule = text_to_speech.TextToSpeechHandler(
            entity_controller=self,
            tts_config=dict(self.config.items('TTS'))
        )
        self.ttsModule.activate()

        # Init Module for AI Roleplay to Animation
        # self.movementModule = movement.MovementHandler(
        #     entity_controller=self,
        #     movement_config=dict(self.config.items('Movement'))
        # )
        # self.movementModule.activate()

        # Init Module for AI Perception Handling
        self.perceptionModule = perception.PerceptionHandler(
            entity_controller=self,
            perception_config=dict(self.config.items('Perception'))
        )
        self.perceptionModule.activate()

        # Init User Controls Module
        self.controlsModule = controls.ControlsHandler(
            entity_controller=self,
            shutdown_func=shutdown,
            controls_keymap_config=dict(self.config.items('Controls.Keymap'))
        )

        return None

    def create_startup_handler(self):
        self.initHandler = EntityInitHandler(
            entity_controller=self,
            entity_id=self.entity_id,
        )
        self.initHandler.activate()

    def update_chara(self, chara):
        self.chara = chara
        # Update in submodules
        # self.backendModule.update_chara(self.chara)
        # self.countenanceModule.update_chara(self.chara)
        self.ttsModule.update_chara(self.chara)
        self.sttModule.update_chara(self.chara)
        # self.movementModule.update_chara(self.chara)

    def shutdown_modules(self):
        # self.backendModule.deactivate()
        self.sttModule.deactivate()
        self.ttsModule.deactivate()
        # self.countenanceModule.deactivate()
        # self.movementModule.deactivate()
        self.controlsModule.deactivate()

        self.connector.stop()


def start_harmony_ai():
    global _config

    # Read Config data from .ini file
    _config = load_config()

    # Actual Plugin Initialization
    logging.info("Initializing VTS-Plugin for Harmony Link")

    # Scene Config - contains references for characters and objects
    scene_config = dict(_config.items('Scene'))

    # Determine user entities to be controlled
    if "user_entity_id" not in scene_config or len(scene_config["user_entity_id"]) == 0:
        _error_abort('Harmony Plugin: User entity id is invalid.')
        return

    # Determine character entities to be controlled
    if "character_entity_id" not in scene_config or len(scene_config["character_entity_id"]) == 0:
        _error_abort('Harmony Plugin: Character entity id/list is invalid.')
        return

    # Setup user entity
    user_entity_id = scene_config["user_entity_id"].strip()
    controller = EntityController(entity_id=user_entity_id, config=_config)
    # Initialize Client modules
    controller.init_modules()
    # Create Startup Init handler
    controller.create_startup_handler()
    # Add to character list
    harmony_globals.active_entities[user_entity_id] = controller
    harmony_globals.user_controlled_entity_id = user_entity_id

    # Setup character entities
    character_list = scene_config["character_entity_id"].split(",")
    for entity_id in character_list:
        # Create entity controller for characters
        entity_id = entity_id.strip()
        controller = EntityController(entity_id=entity_id, config=_config)
        # Initialize Client modules
        controller.init_modules()
        # Create Startup Init handler
        controller.create_startup_handler()
        # Add to character list
        harmony_globals.active_entities[entity_id] = controller

    # Warmup time to allow for the backend threads to connect to the websocket server
    warmup_time = int(_config.get('Harmony', 'start_warmup_time'))
    time.sleep(warmup_time)

    # Initialize Entities on Harmony Link
    for entity_id, controller in harmony_globals.active_entities.items():
        try:
            controller.activate()
        except RuntimeError as e:
            _error_abort(f"Initialization on Harmony Link failed for entity '{entity_id}': {e}")
            return


async def post_init():
    global _config

    # Get VTS Config for setting up entity controller
    vts_config = dict(_config.items('VTS'))

    # Link VTS Controller with Entity controller
    for entity_id, controller in harmony_globals.active_entities.items():

        # Initialize controls module and STT module if it's the user entity
        if entity_id == harmony_globals.user_controlled_entity_id:
            controller.controlsModule.activate()
            controller.sttModule.activate()
        else:
            # Setup VTS Plugin Controller for Entity and set initial values
            vtsc = VTSController(
                endpoint=vts_config["endpoint"].strip(),
                plugin_name=f"Harmony-Link-Plugin-{entity_id}",
            )
            try:
                await vtsc.initialise()
                chara = Chara(controller=vtsc)
                await chara.controller.set_mouth_open(0)
                # Update all controller modules with new chara actor
                controller.update_chara(chara)
            except Exception as e:
                _error_abort(f"Initialization on VTS failed for entity '{entity_id}': {e}")
                return

        # Inform Harmony Link that the scene finished loading for this Entity
        environment_loaded_event = common.HarmonyLinkEvent(
            event_id='environment_loaded',
            event_type=common.EVENT_TYPE_ENVIRONMENT_LOADED,
            status=common.EVENT_STATE_NEW,
            payload={}
        )
        send_success = controller.connector.send_event(environment_loaded_event)
        if send_success:
            logging.info('Harmony Link: Scene Data finished loading for entity "{0}"'.format(entity_id))
        else:
            logging.warning('Harmony Link: Failed to transmit scene loading finished for entity "{0}"'.format(entity_id))


def _error_abort(error):
    logging.error("**** Error aborted ****\n" + error)
    shutdown()


def load_config():
    # read from .ini file
    config = configparser.ConfigParser()
    config_path = os.path.splitext(__file__)[0] + '.ini'
    config.read(config_path)
    return config


def shutdown():
    # Shutdown all Entities
    for controller in harmony_globals.active_entities.values():
        controller.shutdown_modules()

