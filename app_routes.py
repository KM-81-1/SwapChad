from aiohttp import web
from auth import Auth, authorize
from json import JSONDecodeError

import db


# routes class
routes = web.RouteTableDef()


@routes.get('/')
async def landing_page(_request):
    return web.Response(text="Hello World!!!")


@routes.post('/signup')
async def signup(request):
    # Obtaining registration information from the request
    try:
        data = await request.json()
        user_info = data["user_info"]
        credentials = data["credentials"]
        username = credentials["username"]
        password = credentials["password"]
    except (JSONDecodeError, KeyError):
        raise web.HTTPBadRequest

    # Registering user
    try:
        session = db.get_session(request)
        async with session.begin():
            token = await Auth.signup(session, username, password, displayed_name=user_info["displayed_name"])
    except Auth.UsernameIsTakenError:
        raise web.HTTPUnprocessableEntity

    # Sending JWT token to the user
    return web.json_response({'token': token})


@routes.post('/login')
async def login(request):
    # Obtaining login information from the request
    try:
        data = await request.json()
        username = data["username"]
        password = data["password"]
    except (JSONDecodeError, KeyError):
        raise web.HTTPBadRequest

    # Logging user in
    try:
        session = db.get_session(request)
        async with session.begin():
            token = await Auth.login(session, username, password)
    except Auth.UsernameIsTakenError:
        raise web.HTTPBadRequest

    # Sending JWT Bearer token to the user
    return web.json_response({'token': token})


@routes.post('/profile/modify')
@authorize
async def modify_profile(request):
    data = await request.json()
    print("Request from the user %s, authorized via token" % request["user_id"])
    return web.json_response("Authorized")
