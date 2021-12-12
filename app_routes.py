from aiohttp import web
from auth import Auth, authorize
from json import JSONDecodeError
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
import uuid

import db
from chat import Chats

# routes class
routes = web.RouteTableDef()


@routes.get('/')
async def landing_page(_request):
    return web.Response(text="Hello World!!!")


@routes.post('/auth/signup')
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
        async with session:
            token = await Auth.signup(session, username, password, displayed_name=user_info["displayed_name"])
    except Auth.UsernameIsTakenError:
        raise web.HTTPUnprocessableEntity

    # Sending JWT token to the user
    return web.json_response({'token': token})


@routes.post('/auth/login')
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
        async with session:
            token = await Auth.login(session, username, password)
    except Auth.WrongCredentials:
        raise web.HTTPUnauthorized

    # Sending JWT Bearer token to the user
    return web.json_response({'token': token})


@routes.get('/chat/find')
@authorize
async def find_chat(request):
    user_id = request["user_id"]
    chat_id = await request.app["lobby"].find_chat(user_id)
    chat_id = chat_id.hex
    return web.json_response({"chat_id": chat_id})


@routes.get('/chat/abort-search')
@authorize
async def abort_search(request):
    user_id = request["user_id"]
    request.app["lobby"].abort_search(user_id)


@routes.get('/chat/{chat_id}')
@authorize
async def connect_to_chat(request):
    user_id = request["user_id"]

    # Obtaining chat instance
    chat_id = request.match_info["chat_id"]

    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        raise web.HTTPBadRequest

    try:
        chat = request.app["chats"].find_chat(chat_id)
    except Chats.ChatNotFoundError:
        raise web.HTTPNotFound

    # Upgrade connection to websocket
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Start chatting
    await chat.connect(user_id, ws)

    # Exit from chat
    await request.app["chats"].stop(chat_id)


@routes.get('/chat/exit/{chat_id}')
@authorize
async def exit_from_chat(request):
    # Obtaining chat instance
    chat_id = request.match_info["chat_id"]

    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        raise web.HTTPBadRequest

    await request.app["chats"].stop(chat_id)


@routes.post('/profile/modify')
@authorize
async def modify_profile(request):
    # Obtaining profile information from the request
    try:
        data = await request.json()
        displayed_name = data['displayed_name']
        user_id = request['user_id']
        print(user_id)
    except (JSONDecodeError, KeyError):
        raise web.HTTPBadRequest

    # Changing profile data
    session = db.get_session(request)
    async with session:
        user = (await session.execute(select(db.User).filter_by(user_id=user_id))).scalar_one()
        user.displayed_name = displayed_name
        await session.commit()

    return web.Response()


@routes.get('/profile/get/{user_id}')
async def get_profile(request):
    # Get user_id from url
    user_id = request.match_info['user_id']
    try:
        user_id = uuid.UUID(user_id)
    except ValueError:
        raise web.HTTPBadRequest

    # Getting profile data of user with id = user_id
    session = db.get_session(request)
    async with session:
        try:
            user = (await session.execute(select(db.User).filter_by(user_id=user_id))).scalar_one()
            displayed_name = user.displayed_name
        except NoResultFound:
            raise web.HTTPNotFound()

    # Return profile data
    return web.json_response({'displayed_name': displayed_name})
