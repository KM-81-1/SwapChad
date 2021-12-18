from aiohttp import WSMsgType
import logging

from sqlalchemy import select

import db

logger = logging.getLogger(__name__)


class Chat:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.clients = dict()
        self.messages = []
        self.last_message_id = 0
        self.saved_by = set()
        self.saving_session = None

    @staticmethod
    async def try_load_saved(session, chat_id):
        query = select(db.Message).filter_by(chat_id=chat_id)
        result = await session.execute(query)
        messages = result.scalars().all()

        if not messages:
            return None

        new_chat = Chat(chat_id)
        new_chat.messages = [
            Chat.Message(message_id=message.message_id,
                         from_id=message.user_id,
                         text=message.text)
            for message in messages
        ]
        if messages:
            new_chat.last_message_id = messages[-1].message_id
        new_chat.saving_session = session
        return new_chat

    async def save(self, session, by_id, title):
        if self.saved_by:
            instance = await self.try_load_saved_instance(session, by_id)
            if instance:
                instance.title = title
            else:
                self.save_instance(session, by_id, title)

        else:
            self.saving_session = session
            self.save_instance(session, by_id, title)

            for message in self.messages:
                message.save(session, self.chat_id)

            self.saved_by.add(by_id)

    async def proceed(self, user_id, ws):
        self.clients[user_id] = ws

        # Send messages to user
        logger.info("CHAT %s: SENDING MESSAGES (%d) TO USER %s\n...", self.chat_id, len(self.messages), user_id)
        await ws.send_json([message.raw_from_user_perspective(user_id) for message in self.messages])

        logger.info("CHAT %s: MESSAGES SENT, WAITING FOR UPDATES FROM USER %s\n...", self.chat_id, user_id)

        # Handle updates from the user until websocket disconnects
        try:
            async for update in ws:
                if update.type == WSMsgType.TEXT:
                    await self.handle_update(user_id, update.data)
                else:
                    logger.warning("CHAT %s: USER %s SENT NON-TEXT MESSAGE: ", user_id, str(update.data))
        except Exception as e:
            print("WS EXC: " + str(e))

        # Websocket was closed, removing user from the chat
        del self.clients[user_id]
        logger.info("CHAT %s: USER %s HAD LEFT", self.chat_id, user_id)
        for other_user_id, other_ws in self.clients.items():
            logger.info("CHAT %s: \tNOTIFYING USER %s", self.chat_id, user_id)
            await other_ws.send_str("ANON HAD LEFT")
        logger.info("CHAT %s: NOTIFIED ALL OTHER USERS", self.chat_id)

    class Message:
        def __init__(self, message_id, from_id, text):
            self.message_id = message_id
            self.from_id = from_id
            self.text = text

        def raw_from_user_perspective(self, user_id):
            return {
                "message_id": self.message_id,
                "from": ("YOU" if self.from_id == user_id else "ANON"),
                "text": self.text,
            }

        def save(self, session, chat_id):
            new_message = db.Message(chat_id=chat_id,
                                     message_id=self.message_id,
                                     user_id=self.from_id,
                                     text=self.text)
            session.add(new_message)

    async def handle_update(self, from_id, text):
        logger.info("CHAT %s: HANDLING INCOMING MESSAGE FROM USER %s...", self.chat_id, from_id)

        self.last_message_id += 1
        new_message = self.Message(message_id=self.last_message_id,
                                   from_id=from_id,
                                   text=text)
        self.messages.append(new_message)

        for other_user_id, other_ws in self.clients.items():
            if other_user_id != from_id:
                await other_ws.send_str(new_message.text)
                logger.info("CHAT %s: \tBROADCAST MESSAGE TO USER %s", self.chat_id, other_user_id)

        if self.saved_by:
            new_message.save(self.saving_session, self.chat_id)
            await self.saving_session.commit()

        logger.info("CHAT %s: MESSAGE HANDLED\n...", self.chat_id)

    async def try_load_saved_instance(self, session, by_id):
        query = select(db.SavedChat).filter_by(chat_id=self.chat_id,
                                               user_id=by_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    def save_instance(self, session, by_id, title):
        new_saved = db.SavedChat(chat_id=self.chat_id,
                                 user_id=by_id,
                                 title=title)
        session.add(new_saved)

