from os import getenv

from aiohttp import web

routes = web.RouteTableDef()


@routes.get('/')
async def landing_page(_request):
    return web.Response(text="Hello World!!!")


async def create_app():
    app = web.Application()
    app.add_routes(routes)
    return app


if __name__ == '__main__':
    web.run_app(create_app(),
                host=getenv("HOST", "127.0.0.1"),
                port=getenv("PORT", 80))
