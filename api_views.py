import logging
import uuid

from aiohttp.web import json_response, Request, Response
from aiohttp.web_ws import WebSocketResponse
from rororo import openapi_context, OperationTableDef
from rororo.openapi import ObjectDoesNotExist, ValidationError, BasicInvalidCredentials
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

import db
from auth import Auth, jwt_auth
from chat import Chats, Lobby

logger = logging.getLogger(__name__)
operations = OperationTableDef()


@operations.register("signUp")
async def signup(request: Request) -> Response:
    logging.error("\nSIGNUP")
    with openapi_context(request) as context:
        # Obtain registration information from the request
        try:
            user_info = context.data["user_info"]
            public_info = user_info["public"]
            displayed_name = public_info["displayed_name"]
            credentials = context.data["credentials"]
            username = credentials["username"]
            password = credentials["password"]
        except KeyError:
            raise ValidationError()

    # Register user
    try:
        async with db.get_session(request) as session:
            token = await Auth.signup(session, username, password, displayed_name=displayed_name)
    except Auth.UsernameIsTakenError:
        raise ValidationError(message="Username is taken")

    # Send JWT token to the user
    return json_response({'token': token})


@operations.register("logIn")
async def login(request: Request) -> Response:
    logging.error("\nLOGIN")
    with openapi_context(request) as context:
        # Obtain login information from the request
        try:
            username = context.data["username"]
            password = context.data["password"]
        except KeyError:
            raise ValidationError()

    # Login user
    try:
        async with db.get_session(request) as session:
            token = await Auth.login(session, username, password)
    except Auth.WrongCredentials:
        raise BasicInvalidCredentials()

    # Send JWT Bearer token to the user
    return json_response({'token': token})


@operations.register("startSearch")
@jwt_auth
async def start_search(request: Request) -> Response:
    logging.error("\nSTART SEARCH")
    user_id = request["user_id"]
    try:
        chat_id = await request.app["lobby"].find_chat(user_id)
    except Lobby.AlreadySearchingError:
        raise ValidationError(message="Already searching")
    chat_id = chat_id.hex

    return json_response({"chat_id": chat_id})


@operations.register("abortSearch")
@jwt_auth
async def abort_search(request: Request) -> Response:
    logging.error("\nABORT SEARCH")
    user_id = request["user_id"]
    request.app["lobby"].abort_search(user_id)

    return json_response()


@operations.register("joinChat")
@jwt_auth
async def join_chat(request: Request) -> Response:
    logging.error("\nJOIN CHAT")
    user_id = request["user_id"]
    with openapi_context(request) as context:
        chat_id = context.parameters.path["chat_id"]
    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        raise ValidationError()

    # Obtain chat instance
    try:
        chat = request.app["chats"].find_chat(chat_id)
    except Chats.ChatNotFoundError:
        raise ObjectDoesNotExist(label="Chat")

    # Upgrade connection to websocket
    ws = WebSocketResponse()
    await ws.prepare(request)

    # Start chatting
    await chat.connect(user_id, ws)

    # Exit from chat
    await request.app["chats"].stop(chat_id)

    return json_response()


@operations.register("leaveChat")
@jwt_auth
async def leave_chat(request: Request) -> Response:
    logging.error("\nLEAVE CHAT")
    with openapi_context(request) as context:
        chat_id = context.parameters.path["chat_id"]
    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        raise ValidationError()

    await request.app["chats"].stop(chat_id)

    return json_response()


@operations.register("getPublicUserInfo")
async def get_public_user_info(request: Request) -> Response:
    logging.error("\nGET PUBLIC USER INFO")
    with openapi_context(request) as context:
        username = context.parameters.path["username"]

    # Get profile data
    async with db.get_session(request) as session:
        try:
            user = await get_user(session, username=username)
            displayed_name = user.displayed_name
        except NoResultFound:
            raise ObjectDoesNotExist(label="User")

    # Send profile data to the user
    return json_response({'displayed_name': displayed_name})


@operations.register("getAllUserInfo")
@jwt_auth
async def get_all_user_info(request: Request) -> Response:
    logging.error("\nGET ALL USER INFO")
    user_id = request['user_id']

    # Get profile data
    async with db.get_session(request) as session:
        try:
            user = await get_user(session, user_id=user_id)
            displayed_name = user.displayed_name
        except NoResultFound:
            raise ObjectDoesNotExist(label="User")

    # Send profile data to the user
    public_data = {'displayed_name': displayed_name}
    return json_response({'public': public_data})


@operations.register("modifyAllUserInfo")
@jwt_auth
async def modify_all_user_info(request: Request) -> Response:
    logging.error("\nMODIFY ALL USER INFO")
    user_id = request['user_id']
    with openapi_context(request) as context:
        try:
            public_data = context.data['public']
            displayed_name = public_data['displayed_name']
        except KeyError:
            raise ValidationError()

    # Change profile data
    async with db.get_session(request) as session:
        user = await get_user(session, user_id=user_id)
        user.displayed_name = displayed_name
        await session.commit()

    return json_response()


async def get_user(session, **filter_kwargs):
    logging.error("\n__GET USER")
    query = select(db.User).filter_by(**filter_kwargs)
    result = await session.execute(query)
    user = result.scalar_one()
    return user
