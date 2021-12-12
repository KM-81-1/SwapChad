from os import environ, getenv
import aiohttp.web
from aiohttp import web

import db
from auth import Auth, authorize

# routes class
routes = web.RouteTableDef()


@routes.get('/')
async def landing_page(_request):
    return web.Response(text="Hello World!!!")


@routes.post('/signup')
async def signup(request):
    data = await request.json()

    # Obtaining registration information from the request
    try:
        user_info = data["user_info"]
        credentials = data["credentials"]
        username = credentials["username"]
        password = credentials["password"]
    except KeyError:
        raise aiohttp.web.HTTPBadRequest

    # Registering user
    try:
        session = db.get_session(request)
        async with session.begin():
            token = await Auth.signup(session, username, password, displayed_name=user_info["displayed_name"])
    except Auth.UsernameIsTakenError:
        raise aiohttp.web.HTTPUnprocessableEntity

    # Sending JWT token to the user
    return web.json_response({'token': token})


@routes.post('/login')
async def login(request):
    data = await request.json()

    # Obtaining login information from the request
    try:
        username = data["username"]
        password = data["password"]
    except KeyError:
        raise aiohttp.web.HTTPBadRequest

    # Logging user in
    try:
        session = db.get_session(request)
        async with session.begin():
            token = await Auth.login(session, username, password)
    except Auth.UsernameIsTakenError:
        raise aiohttp.web.HTTPBadRequest

    # Sending JWT Bearer token to the user
    return web.json_response({'token': token})


@routes.post('/profile/modify')
@authorize
async def modify_profile(request):
    data = await request.json()
    print("Request from the user %s, authorized via token" % request["user_id"])
    return web.json_response("Authorized")


async def create_app():
    app = web.Application()
    await db.connect(app, environ["DATABASE_URL"])
    app.add_routes(routes)
    return app


if __name__ == '__main__':
    web.run_app(create_app(),
                host=getenv("HOST", "127.0.0.1"),
                port=getenv("PORT", 80))
