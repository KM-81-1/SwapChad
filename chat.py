import asyncio
import uuid


class Chat:
    def __init__(self):
        self.stopped = False
        self.clients = dict()
        self.runner = None

    async def stop(self):
        if self.stopped:
            return
        self.stopped = True
        for client in self.clients.values():
            try:
                await client.send_str("CHAT STOPPED")
                await client.close()
            except ConnectionResetError:
                pass

    async def handle_update(self, from_id, update):
        for user_id, client in self.clients.items():
            if user_id != from_id:
                await client.send_str("ECHO: " + str(update))

    async def connect(self, user_id, ws):
        """ Adds user to the chat """
        self.clients[user_id] = ws

        async for update in ws:
            print(update)
            await self.handle_update(user_id, update)

        return ws


class PendingUser:
    def __init__(self, user_id):
        self.user_id = user_id
        self.event = asyncio.Event()
        self.chat_id = None

    async def obtain_chat(self):
        await self.event.wait()
        return self.chat_id

    def send_chat_id(self, chat_id):
        self.chat_id = chat_id
        self.event.set()


class Lobby:
    def __init__(self, chats):
        self.waiting = []
        self.chats = chats

    def match(self, new_pending_user):
        for i, _potential_companion in enumerate(self.waiting):
            if True:  # TODO matching
                (client_1, client_2) = new_pending_user, self.waiting.pop(i)
                new_chat_id = self.chats.start()
                client_1.send_chat_id(new_chat_id)
                client_2.send_chat_id(new_chat_id)
                return
        self.waiting.append(new_pending_user)

    async def find_chat(self, user_id):
        new_pending_user = PendingUser(user_id)
        self.match(new_pending_user)
        return await new_pending_user.obtain_chat()

    def abort_search(self, user_id):
        for i, pending_user in enumerate(self.waiting):
            if pending_user.user_id == user_id:
                self.waiting.pop(i)
                break


class Chats:
    def __init__(self):
        self.chats = dict()

    class ChatNotFoundError(Exception):
        pass

    def start(self):
        new_chat = Chat()
        new_chat_id = uuid.uuid4()
        self.chats[new_chat_id] = new_chat
        return new_chat_id

    async def stop(self, chat_id):
        try:
            await self.chats[chat_id].stop()
            self.chats.pop(chat_id)
        except KeyError:
            pass

    def find_chat(self, chat_id):
        try:
            return self.chats[chat_id]
        except KeyError:
            raise Chats.ChatNotFoundError()
