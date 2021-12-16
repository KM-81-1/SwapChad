import uuid
from asyncio import Event
from aiohttp import WSMsgType
import logging

from aiohttp.http_websocket import WS_CLOSING_MESSAGE

logger = logging.getLogger(__name__)


class Chat:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.clients = dict()
        self.is_closing = Event()

    async def connect_and_stay(self, user_id, ws):
        self.clients[user_id] = ws

        logger.info("CHAT %d: USER %d CONNECTED", self.chat_id, user_id)

        try:
            async for update in ws:
                if update.type == WSMsgType.TEXT:
                    await self.handle_message(user_id, update)
        except Exception as e:
            print("WS EXC: " + str(e))

        logger.info("CHAT %s: USER %s WEBSOCKET WAS CLOSED", self.chat_id, user_id)
        await self.close(user_id)
        logger.info("CHAT %s: USER %s EXITS", self.chat_id, user_id)

    async def close(self, by_user_id):
        if not self.is_closing.is_set():
            self.is_closing.set()
            logger.info("CHAT %s: USER %s SET CLOSING FLAG, CLOSING ALL WEBSOCKETS", self.chat_id, by_user_id)
            for user_id, ws in self.clients.items():
                logger.info("CHAT %s: \tCLOSING USER %s WEBSOCKET", self.chat_id, user_id)
                ws._reader.feed_data(WS_CLOSING_MESSAGE, 0)
            logger.info("CHAT %s: USER %s CLOSED ALL WEBSOCKETS", self.chat_id, by_user_id)

    async def handle_message(self, from_id, update):
        logger.info("CHAT %s: HANDLING UPDATE FROM USER %s", self.chat_id, from_id)
        for user_id, ws in self.clients.items():
            if user_id != from_id:
                await ws.send_str(update.data)
                logger.info("CHAT %s: \tBROADCAST TO USER %s", self.chat_id, user_id)


class ChatsList:
    def __init__(self):
        self.chats = {}

    class ChatNotFoundError(Exception):
        pass

    def create_new(self):
        new_chat_id = uuid.uuid4()
        new_chat = Chat(new_chat_id)
        self.chats[new_chat_id] = new_chat
        return new_chat_id

    def find_chat(self, chat_id):
        try:
            return self.chats[chat_id]
        except KeyError:
            raise self.ChatNotFoundError()
