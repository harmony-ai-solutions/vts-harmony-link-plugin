# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# Connector Module
# This module uses WebSocket connections to interface with Harmony Link's Event Backend

import asyncio
import logging

import websockets
import json

from harmony_modules.common import HarmonyLinkEvent


# Define Classes
class HarmonyEventJSONEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__


class ConnectorEventHandler:
    def __init__(self, ws_endpoint, shutdown_func):
        # Setup Config Params
        self.ws_endpoint = ws_endpoint

        # Setup Connector
        self.eventHandlers = []
        self.shutdown_func = shutdown_func
        self.running = False
        self.websocket = None
        self.send_queue = asyncio.Queue()
        self.task = None
        self.event_loop = None

    def start(self):
        logging.debug('Starting ConnectorEventHandler')
        self.running = True
        self.event_loop = asyncio.get_running_loop()
        self.task = asyncio.create_task(self.run())

    async def run(self):
        try:
            async with websockets.connect(self.ws_endpoint) as websocket:
                self.websocket = websocket
                consumer_task = asyncio.create_task(self.consumer_handler())
                producer_task = asyncio.create_task(self.producer_handler())
                await asyncio.gather(consumer_task, producer_task)
        except Exception as e:
            logging.error(f'WebSocket connection failed: {e}')
            self.shutdown_func()

    async def consumer_handler(self):
        try:
            async for message in self.websocket:
                # TODO: Check if this should be creating a task instead for better performance
                await self.process_event_message(message)
        except Exception as e:
            logging.error(f'Error in consumer_handler: {e}')
            self.shutdown_func()

    async def producer_handler(self):
        try:
            while self.running:
                event, future = await self.send_queue.get()
                message_string = json.dumps(event, cls=HarmonyEventJSONEncoder)
                try:
                    await self.websocket.send(message_string)
                    future.set_result(True)
                except Exception as e:
                    future.set_exception(e)
                    logging.error(f"Failed to send event: {e}")
        except Exception as e:
            logging.error(f'Error in producer_handler: {e}')
            self.shutdown_func()

    async def process_event_message(self, message_string):
        if len(message_string) == 0:
            logging.warning('Message event was empty!')
            return

        try:
            message_json = json.loads(message_string)
            logging.debug(f'Event message received: {message_string}')
            message = HarmonyLinkEvent(**message_json)
            await self.handle_event(event=message)
        except ValueError as e:
            logging.error(f'Failed to read event message: {str(e)}')
            logging.error(f'Original message: {message_string}')

    def stop(self):
        logging.debug('Stopping ConnectorEventHandler')
        self.running = False
        # Close the WebSocket connection
        if self.websocket:
            asyncio.create_task(self.websocket.close())

        # Deactivate event handlers
        for event_handler in self.eventHandlers:
            event_handler.deactivate()

        # Cancel the run task if it's running
        if self.task:
            self.task.cancel()

    def register_event_handler(self, event_handler):
        if event_handler not in self.eventHandlers:
            self.eventHandlers.append(event_handler)

    def unregister_event_handler(self, event_handler):
        if event_handler in self.eventHandlers:
            self.eventHandlers.remove(event_handler)

    async def send_event(self, event):
        # Create a Future associated with the current event loop
        send_event_future = self.event_loop.create_future()
        # Enqueue the event and its Future to be sent by the producer handler
        self.send_queue.put_nowait((event, send_event_future))
        try:
            send_success = await send_event_future
            return send_success
        except Exception as e:
            raise RuntimeError(f"Failed to send event to Harmony Link: {e}")

    async def handle_event(self, event):
        if not isinstance(event, HarmonyLinkEvent):
            if not isinstance(event, str):
                event = json.dumps(event, cls=HarmonyEventJSONEncoder)
            logging.warning(f'Invalid event received. Data: {event}')
        else:
            for event_handler in self.eventHandlers:
                await event_handler.handle_event(event)
