import asyncio
from os import environ, getenv
from aiohttp import web

import db
from chat import Lobby, Chats


from app_routes import routes


async def create_components(app):
    chats = Chats()
    app["chats"] = chats

    lobby = Lobby(chats)
    app["lobby"] = lobby


async def create_app():
    app = web.Application()
    await db.connect(app, environ["DATABASE_URL"])
    app.add_routes(routes)
    app.on_startup.append(create_components)
    return app


if __name__ == '__main__':
    web.run_app(create_app(),
                host=getenv("HOST", "127.0.0.1"),
                port=getenv("PORT", 80))
