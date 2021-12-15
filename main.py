from pathlib import Path
from os import getenv
from typing import Callable, Awaitable
from aiohttp import web
import aiohttp_swagger
import rororo
import logging

import db
from chat import Lobby, Chats
import api_views


async def create_components(app):
    chats = Chats()
    app["chats"] = chats

    lobby = Lobby(chats)
    app["lobby"] = lobby


@web.middleware
async def error_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException as exc:
        logging.error(exc)
        print()
        return exc


async def create_app():
    app = web.Application(middlewares=[error_middleware])
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("asyncio.access").setLevel(logging.DEBUG)

    # Connect to DB
    await db.connect(app, getenv("DATABASE_URL"))

    # Initialize rororo lib
    import locale
    if "LC_ALL" in locale.__dict__:
        locale.__dict__["LC_MESSAGES"] = locale.LC_ALL  # Dirty workaround
    rororo.setup_settings(
        app,
        rororo.BaseSettings(),
        loggers=("aiohttp", "aiohttp_middlewares", "petstore", "rororo"),
        remove_root_handlers=True,
    )

    rororo.setup_openapi(
        app,
        Path(__file__).parent / "openapi.yaml",
        api_views.operations,
        cors_middleware_kwargs={"allow_all": True},
    )

    # Initialize aiohttp_swagger lib
    def _swagger_def_def_decor(_def_func):
        def def_func(_request):
            return web.HTTPTemporaryRedirect('/api/openapi.json')
        return def_func
    from typing import Optional
    _swagger_def_def_decor: Optional[...] = _swagger_def_def_decor
    aiohttp_swagger.setup_swagger(
        app,
        swagger_url="/api/docs",
        swagger_def_decor=_swagger_def_def_decor,
        ui_version=3,
    )

    # Serve static files
    app.router.add_static("/web", "static")

    # Redirect to landing
    async def _landing_redirect(_request):
        return web.HTTPTemporaryRedirect('web/index.html')
    app.router.add_route("get", "/", handler=_landing_redirect)

    # Binding initialization coroutines
    app.on_startup.append(create_components)

    return app


if __name__ == '__main__':
    web.run_app(create_app(),
                host=getenv("HOST", "127.0.0.1"),
                port=getenv("PORT", 80))
