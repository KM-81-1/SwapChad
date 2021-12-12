from os import environ, getenv
from aiohttp import web

import db


from app_routes import routes


async def create_app():
    app = web.Application()
    await db.connect(app, environ["DATABASE_URL"])
    app.add_routes(routes)
    return app


if __name__ == '__main__':
    web.run_app(create_app(),
                host=getenv("HOST", "127.0.0.1"),
                port=getenv("PORT", 80))
