import logging
import uuid

from aiohttp import WSCloseCode
from aiohttp.web import json_response, Request, Response
from aiohttp.web_exceptions import HTTPBadRequest
from aiohttp.web_ws import WebSocketResponse
from rororo import openapi_context, OperationTableDef
from rororo.openapi import ObjectDoesNotExist, ValidationError, BasicInvalidCredentials, BasicSecurityError
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

import db
from auth import Auth, jwt_auth
from chat import Chats, Lobby

logger = logging.getLogger(__name__)
operations = OperationTableDef()


@operations.register("signUp")
async def signup(request: Request) -> Response:
    logging.error("\t\tSIGNUP")
    with openapi_context(request) as context:
        # Obtain registration information from the request
        try:
            displayed_name = context.data["displayed_name"]
            username = context.data["username"]
            password = context.data["password"]
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
    logging.error("\t\tLOGIN")

    # Obtain login information from the request
    with openapi_context(request) as context:
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
        raise BasicInvalidCredentials(headers={
            "WWW-Authenticate": "xBasic"
        })

    # Send JWT Bearer token to the user
    return json_response({'token': token})


@operations.register("startSearch")
@jwt_auth
async def start_search(request: Request) -> Response:
    logging.error("\t\tSTART SEARCH")
    user_id = request["user_id"]
    logging.error("GOT USER_ID")
    try:
        chat_id = await request.app["lobby"].find_chat(user_id)
        logging.error("FOUND CHAT")
    except Lobby.AlreadySearchingError:
        logging.error("AlreadySearchingError")
        raise ValidationError(message="Already searching")
    chat_id = chat_id.hex

    logging.error("EXITING, SENDING CHAT " + str(chat_id))

    return json_response({"chat_id": chat_id})


@operations.register("abortSearch")
@jwt_auth
async def abort_search(request: Request) -> Response:
    logging.error("\t\tABORT SEARCH")
    user_id = request["user_id"]
    request.app["lobby"].abort_search(user_id)

    return json_response()


@operations.register("joinChat")
async def join_chat(request: Request) -> Response:
    logging.error("\t\tJOIN CHAT")
    with openapi_context(request) as context:
        chat_id = context.parameters.path["chat_id"]
    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        raise ValidationError()

    logging.error("\t\tGOT CHAT ID")
    # Upgrade connection to websocket
    ws = WebSocketResponse()
    try:
        await ws.prepare(request)
    except HTTPBadRequest:
        raise ValidationError(message="Websocket connection is required")

    logging.error("\t\tMADE WEBSOCKET")
    # Obtain chat instance
    try:
        chat = request.app["chats"].find_chat(chat_id)
    except Chats.ChatNotFoundError:
        await ws.close(code=WSCloseCode.UNSUPPORTED_DATA, message="Chat not found".encode("utf-8"))
        raise ObjectDoesNotExist(label="Chat")

    logging.error("\t\tOBTAINED CHAT")

    # Receive token from websocket
    token = await ws.receive_str()

    logging.error("\t\tRECEIVED TOKEN")

    # Validate and obtain user_id from it
    try:
        user_id = Auth.verify(token)
    except Auth.InvalidToken:
        await ws.close(code=WSCloseCode.UNSUPPORTED_DATA, message="Invalid JWT token".encode("utf-8"))
        logging.error("INVALID JWT TOKEN")
        raise BasicSecurityError(message="Invalid JWT token")

    logging.error("\t\tTOKEN CONFIRMED")

    # Start chatting
    await chat.connect(user_id, ws)

    logging.error("\t\tCONNECTED TO THE CHAT")

    # Exit from chat
    await request.app["chats"].stop(chat_id)

    logging.error("\t\tEXIT FROM THE CHAT")

    await ws.close()

    logging.error("\t\tCLOSED WEBHOOK, END")

    return json_response()


@operations.register("leaveChat")
@jwt_auth
async def leave_chat(request: Request) -> Response:
    logging.error("\t\tLEAVE CHAT")
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
    logging.error("\t\tGET PUBLIC USER INFO")
    with openapi_context(request) as context:
        username = context.parameters.path["username"]

    # Get profile info
    async with db.get_session(request) as session:
        try:
            user = await get_user(session, username=username)
            displayed_name = user.displayed_name
        except NoResultFound:
            raise ObjectDoesNotExist(label="User")

    # Send profile data to the user
    return json_response({
        'displayed_name': displayed_name,
    })


@operations.register("getAllUserInfo")
@jwt_auth
async def get_all_user_info(request: Request) -> Response:
    logging.error("\t\tGET ALL USER INFO")
    user_id = request['user_id']

    # Get profile data
    async with db.get_session(request) as session:
        try:
            user = await get_user(session, user_id=user_id)
            displayed_name = user.displayed_name
            username = user.username
        except NoResultFound:
            raise ObjectDoesNotExist(label="User")

    # Send profile data to the user
    return json_response({
        'public': {
            'displayed_name': displayed_name
        },
        'private': {
            'username': username
        },
    })


@operations.register("modifyAllUserInfo")
@jwt_auth
async def modify_all_user_info(request: Request) -> Response:
    logging.error("\t\tMODIFY ALL USER INFO")
    user_id = request['user_id']
    with openapi_context(request) as context:
        try:
            public_info = context.data['public']
            displayed_name = public_info['displayed_name']
            private_info = context.data['private']
            username = private_info['username']
        except KeyError:
            raise ValidationError()

    # Change profile data
    async with db.get_session(request) as session:
        user = await get_user(session, user_id=user_id)
        user.displayed_name = displayed_name
        user.username = username
        await session.commit()

    return json_response()


async def get_user(session, **filter_kwargs):
    query = select(db.User).filter_by(**filter_kwargs)
    result = await session.execute(query)
    user = result.scalar_one()
    return user
