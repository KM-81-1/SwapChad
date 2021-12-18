import uuid
from asyncio import Event
import logging

import db
from chat import Chat

logger = logging.getLogger(__name__)


class Lobby:
    def __init__(self):
        self.chats = {}
        self.pending = None

    class Pending:
        def __init__(self, user_id):
            self.user_id = user_id
            self.chat_id = None
            self.event = Event()

        def send(self, chat_id):
            self.chat_id = chat_id
            self.event.set()

        async def obtain(self):
            await self.event.wait()
            return self.chat_id

    class AlreadySearchingError(Exception):
        pass

    class WasNotSearchingError(Exception):
        pass

    async def start_search_and_wait(self, user_id):
        if self.pending:
            if self.pending.user_id == user_id:
                raise self.AlreadySearchingError()

            new_chat_id = uuid.uuid4()
            self.chats[new_chat_id] = Chat(new_chat_id)

            pending = self.pending
            self.pending = None

            logger.info("WAS PENDING, CREATED NEW CHAT %s, SENDING AND RETURNING", new_chat_id)

            pending.send(new_chat_id)
            return new_chat_id

        else:
            pending = self.Pending(user_id)
            self.pending = pending

            logger.info("NO PENDING, CREATED NEW, WAITING\n...")

            chat_id = await pending.obtain()

            if chat_id is None:
                logger.info("FINISHED WAITING, CHAT NOT FOUND (ABORTED)")
            else:
                logger.info("FINISHED WAITING, GOT CHAT %s", chat_id)

            return chat_id

    def abort_search(self, user_id):
        if self.pending is None or self.pending.user_id != user_id:
            raise self.WasNotSearchingError()

        self.pending.send(None)
        self.pending = None

    async def get_chat(self, request, chat_id):
        chat = self.chats.get(chat_id)
        if chat:
            return chat

        chat = await Chat.try_load_saved(db.get_session(request), chat_id)
        if chat:
            self.chats[chat_id] = chat
            return chat

        return None

    async def proceed_with_chat(self, chat, user_id, ws):
        await chat.proceed(user_id, ws)
        if not chat.clients:
            del self.chats[chat.chat_id]
            logger.info("CHAT %s: ALL USERS HAVE LEFT, CHAT WAS UNLOADED", chat.chat_id)
