import logging
import uuid

from aiohttp.web import json_response, Request, Response
from aiohttp.web_ws import WebSocketResponse
from rororo import openapi_context, OperationTableDef
from rororo.openapi import ObjectDoesNotExist, ValidationError, BadRequest, BasicInvalidCredentials
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

import db
from auth import Auth, jwt_auth
from chat import Chats

logger = logging.getLogger(__name__)
operations = OperationTableDef()


@operations.register("signUp")
async def signup(request: Request) -> Response:
    with openapi_context(request) as context:
        # Obtain registration information from the request
        try:
            user_info = context.data["user_info"]
            credentials = context.data["credentials"]
            username = credentials["username"]
            password = credentials["password"]
        except KeyError:
            raise ValidationError()

    # Register user
    try:
        async with db.get_session(request) as session:
            token = await Auth.signup(session, username, password, displayed_name=user_info["displayed_name"])
    except Auth.UsernameIsTakenError:
        raise BadRequest(message="Username is taken")

    # Send JWT token to the user
    return json_response({'token': token})


@operations.register("logIn")
async def login(request: Request) -> Response:
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


@operations.register("findChat")
@jwt_auth
async def find_chat(request: Request) -> Response:
    user_id = request["user_id"]
    chat_id = await request.app["lobby"].find_chat(user_id)
    chat_id = chat_id.hex

    return json_response({"chat_id": chat_id})


@operations.register("abortSearch")
@jwt_auth
async def abort_search(request: Request) -> Response:
    user_id = request["user_id"]
    request.app["lobby"].abort_search(user_id)

    return json_response()


@operations.register("joinChat")
@jwt_auth
async def join_chat(request: Request) -> Response:
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
    with openapi_context(request) as context:
        chat_id = context.parameters.path["chat_id"]
    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        raise ValidationError()

    await request.app["chats"].stop(chat_id)

    return json_response()


@operations.register("getProfile")
async def get_profile(request: Request) -> Response:
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


@operations.register("modifyProfile")
@jwt_auth
async def modify_profile(request: Request) -> Response:
    user_id = request['user_id']
    with openapi_context(request) as context:
        try:
            displayed_name = context.data['displayed_name']
        except KeyError:
            raise ValidationError()

    # Change profile data
    async with db.get_session(request) as session:
        user = await get_user(session, user_id=user_id)
        user.displayed_name = displayed_name
        await session.commit()

    return json_response()


async def get_user(session, **filter_kwargs):
    query = select(db.User).filter_by(**filter_kwargs)
    result = await session.execute(query)
    user = result.scalar_one()
    return user