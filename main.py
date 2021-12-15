import sys
from pathlib import Path
from os import getenv
from typing import Callable, Awaitable
from aiohttp import web
import aiohttp_swagger
import rororo
import logging
import logging.config

import db
from chat import ChatsList
from lobby import Lobby
import api_views
import context_id_hook


async def create_components(app):
    chats_list = ChatsList()
    app["chats_list"] = chats_list

    lobby = Lobby(chats_list)
    app["lobby"] = lobby


@web.middleware
async def error_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException as exc:
        logging.getLogger("rororo").error(exc.text)
        return exc


def init_logging():
    context_id_hook.setup()

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "DEBUG",
                "stream": sys.stdout,
            },
        },
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)8s %(requestIdPrefix)-10s %(name)-20s %(message)s"
            },
            "without_time": {
                "format": "%(message)s"
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["stdout"],
            "formatters": ["naked"],
        }
    })

    for handler in logging.getLogger().handlers:
        _emit = handler.emit

        def emit(record):
            if (str(record.__dict__.get("first_request_line")) + ".").split()[0] == "OPTIONS":
                return
            _emit(record)
            if record.__dict__.get("name") == 'aiohttp.access':
                print()

        handler.emit = emit


async def create_app():

    init_logging()

    app = web.Application(middlewares=[context_id_hook.middleware, error_middleware])

    # Connect to DB
    await db.connect(app, getenv("DATABASE_URL"))

    # Initialize rororo lib
    import locale
    if "LC_ALL" in locale.__dict__:
        locale.__dict__["LC_MESSAGES"] = locale.LC_ALL  # Dirty workaround
    rororo.setup_settings(
        app,
        rororo.BaseSettings(),
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
                port=getenv("PORT", 80),
                access_log_class=context_id_hook.AccessLogClass)
