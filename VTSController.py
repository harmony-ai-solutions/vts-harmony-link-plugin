import logging
import uuid
from json import dumps, loads
from os import getenv

import websockets
from dotenv import load_dotenv, set_key


class VTSController:
    def __init__(
        self,
        endpoint: str = "ws://localhost:8001",
        plugin_name: str = 'Harmony-Link-Plugin',
        plugin_developer: str = 'HarmonyAI-Solutions'
    ) -> None:
        self.base_info = {
            'pluginName': plugin_name,
            'pluginDeveloper': plugin_developer
        }
        self.endpoint = endpoint
        self.vts_token = None
        self.websocket = None

    async def send_request(self, message_type: str = 'APIStateRequest', data: dict = None) -> dict:
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": uuid.uuid4().hex,
            "messageType": message_type,
            "data": data
        }
        await self.websocket.send(dumps(request))
        result = await self.websocket.recv()
        return loads(result)

    async def authentication(self) -> None:
        self.update_dotenv()

        if not self.vts_token:
            logging.debug("VTS Token not set, requesting new token...")
            res = await self.send_request(message_type='AuthenticationTokenRequest', data=self.base_info)
            if res['messageType'] == 'APIError':
                raise Exception(f"Error occured:\n\t{res['data']['message']}")
            self.__update_token(res['data']['authenticationToken'])
            logging.debug("VTS Token updated")
            return

        res = await self.send_request(message_type='AuthenticationRequest',
                                      data={**self.base_info, 'authenticationToken': self.vts_token})
        if not res['data']['authenticated']:
            raise ConnectionError(f"Couldn't connect to the API: {res['data']['reason']}")

    async def initialise(self) -> None:
        self.update_dotenv()
        try:
            self.websocket = await websockets.connect(self.endpoint)
            res = await self.send_request(message_type='APIStateRequest')
        except Exception as e:
            logging.error(f"WebSocket initialization error: {e}")
            raise

        if not res['data']['currentSessionAuthenticated']:
            try:
                await self.authentication()
            except Exception as e:
                logging.error(f"Authentication error: {e}")
                raise

    async def inject_params(self, parameters: list) -> None:
        data = {
            "faceFound": False,
            "mode": "set",
            "parameterValues": list(dict(id=param[0], value=param[1]) for param in parameters)
        }

        await self.send_request(message_type='InjectParameterDataRequest', data=data)

    async def set_mouth_open(self, mouth_open: float = 0.0) -> None:
        await self.inject_params([['MouthOpen', mouth_open]])

    def update_dotenv(self) -> None:
        load_dotenv(override=True)
        self.vts_token = getenv("VTS_TOKEN")

    def __update_token(self, token: str) -> None:
        self.vts_token = token
        set_key('.env', 'VTS_TOKEN', token)
