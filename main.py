from os import getenv

from aiohttp import web

routes = web.RouteTableDef()


@routes.get('/')
async def landing_page(_request):
    return web.Response(text="Hello World!!!")


def main():
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app,
                host=getenv("HOST", "127.0.0.1"),
                port=getenv("PORT", 80))


if __name__ == '__main__':
    main()
