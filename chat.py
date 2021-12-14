import asyncio
import uuid
from aiohttp import WSMsgType


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
        print("\t\tUPDATE FROM %s: %s" % (str(from_id), str(update)))
        if update.type == WSMsgType.TEXT:
            for user_id, client in self.clients.items():
                if user_id != from_id:
                    await client.send_str(update.data)

    async def connect(self, user_id, ws):
        """ Adds user to the chat """
        self.clients[user_id] = ws

        async for update in ws:
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

    class AlreadySearchingError(Exception):
        pass

    def match(self, new_pending_user):
        print("\t\tTRYING TO MATCH %s" % str(new_pending_user.user_id))
        for i, _potential_companion in enumerate(self.waiting):
            if True:  # TODO matching
                print("\t\tMATCHED WITH %s" % str(_potential_companion.user_id))
                (client_1, client_2) = new_pending_user, self.waiting.pop(i)
                new_chat_id = self.chats.start()
                client_1.send_chat_id(new_chat_id)
                client_2.send_chat_id(new_chat_id)
                return
        print("\t\tNO COMPANIONS FOR %s, WAITING..." % str(new_pending_user.user_id))
        self.waiting.append(new_pending_user)

    async def find_chat(self, user_id):
        print("\t\tFINDING CHAT FOR %s" % str(user_id))
        for i, waiting_user in enumerate(self.waiting):
            if waiting_user.user_id == user_id:
                self.waiting.pop(i)
                print("\t\tFOUND OLD FOR %s, REMOVING" % str(user_id))
                raise Lobby.AlreadySearchingError
        print("\t\tCALLING MATCH FOR %s" % str(user_id))
        new_pending_user = PendingUser(user_id)
        self.match(new_pending_user)
        print("\t\tFOUND CHAT FOR %s" % str(user_id))
        return await new_pending_user.obtain_chat()

    def abort_search(self, user_id):
        for i, pending_user in enumerate(self.waiting):
            if pending_user.user_id == user_id:
                print("\t\tABORTED SEARCH FOR %s" % str(user_id))
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
