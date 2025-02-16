# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# Connector Module
# This module uses WebSocket connections to interface with Harmony Link's Event Backend

import asyncio
import websockets
import json
from threading import Thread

from harmony_modules.common import HarmonyLinkEvent


# Define Classes
class HarmonyEventJSONEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__


class ConnectorEventHandler:
    def __init__(self, ws_endpoint, shutdown_func, game):
        # Setup Config Params
        self.ws_endpoint = ws_endpoint

        # Setup Connector
        self.eventHandlers = []
        self.shutdown_func = shutdown_func
        self.game = game
        self.running = False
        self.event_loop = None
        self.thread = None
        self.websocket = None
        self.send_queue = asyncio.Queue()

    def start(self):
        print('Starting ConnectorEventHandler')
        self.running = True
        self.event_loop = asyncio.new_event_loop()
        self.thread = Thread(target=self.event_loop.run_until_complete, args=(self.run(),))
        self.thread.start()

    async def run(self):
        try:
            async with websockets.connect(self.ws_endpoint) as websocket:
                self.websocket = websocket
                consumer_task = asyncio.ensure_future(self.consumer_handler())
                producer_task = asyncio.ensure_future(self.producer_handler())
                done, pending = await asyncio.wait(
                    [consumer_task, producer_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
        except Exception as e:
            print(f'WebSocket connection failed: {e}')
            self.shutdown_func(self.game)

    async def consumer_handler(self):
        while self.running:
            try:
                message_string = await self.websocket.recv()
                self.process_event_message(message_string)
            except websockets.exceptions.ConnectionClosed:
                print('WebSocket connection closed')
                self.shutdown_func(self.game)
                break

    async def producer_handler(self):
        while self.running:
            event = await self.send_queue.get()
            message_string = json.dumps(event, cls=HarmonyEventJSONEncoder)
            await self.websocket.send(message_string)

    def process_event_message(self, message_string):
        if len(message_string) == 0:
            print('Warning: Message event was empty!')
            return

        try:
            message_json = json.loads(message_string)
            print(f'DEBUG: Event message received: {message_string}')
            message = HarmonyLinkEvent(**message_json)
            self.handle_event(event=message)
        except ValueError as e:
            print(f'Failed to read event message: {str(e)}')
            print(f'Original message: {message_string}')

    def stop(self):
        print('Stopping ConnectorEventHandler')
        self.running = False
        # Wait for thread to finish
        if self.thread.is_alive():
            self.event_loop.call_soon_threadsafe(self.event_loop.stop)
            self.thread.join()
        # Deactivate event handlers
        for event_handler in self.eventHandlers:
            event_handler.deactivate()

    def register_event_handler(self, event_handler):
        if event_handler not in self.eventHandlers:
            self.eventHandlers.append(event_handler)

    def unregister_event_handler(self, event_handler):
        if event_handler in self.eventHandlers:
            self.eventHandlers.remove(event_handler)

    def send_event(self, event):
        # Enqueue the event to be sent by producer handler
        asyncio.run_coroutine_threadsafe(self.send_queue.put(event), self.event_loop)

    def handle_event(self, event):
        if not isinstance(event, HarmonyLinkEvent):
            if not isinstance(event, str):
                event = json.dumps(event, cls=HarmonyEventJSONEncoder)
            print(f'Warning: Invalid event received. Data: {event}')
        else:
            for event_handler in self.eventHandlers:
                event_handler.handle_event(event)