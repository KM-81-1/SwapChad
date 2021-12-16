import logging
import uuid
from aiohttp import WSCloseCode
from aiohttp.web import json_response, Request, Response
from aiohttp.web_exceptions import HTTPBadRequest
from aiohttp.web_ws import WebSocketResponse
from rororo import openapi_context, OperationTableDef
from rororo.openapi import ObjectDoesNotExist, ValidationError, BasicInvalidCredentials
from sqlalchemy import select, delete
from sqlalchemy.exc import NoResultFound

import db
from lobby import Lobby
from chat import ChatsList
from auth import Auth, jwt_auth

logger = logging.getLogger(__name__)
operations = OperationTableDef()


@operations.register("signUp")
async def signup(request: Request) -> Response:
    # Obtain registration information from the request
    with openapi_context(request) as context:
        try:
            displayed_name = context.data["displayed_name"]
            username = context.data["username"]
            password = context.data["password"]
        except KeyError:
            raise ValidationError(message="Wrong body scheme")

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
    # Obtain login information from the request
    with openapi_context(request) as context:
        try:
            username = context.data["username"]
            password = context.data["password"]
        except KeyError:
            raise ValidationError(message="Wrong body scheme")

    # Login user
    try:
        async with db.get_session(request) as session:
            token = await Auth.login(session, username, password)
    except Auth.WrongCredentials:
        raise BasicInvalidCredentials(headers={"WWW-Authenticate": "xBasic"})

    # Send JWT Bearer token to the user
    return json_response({'token': token})


@operations.register("startSearch")
@jwt_auth
async def start_search(request: Request) -> Response:
    user_id = request["user_id"]
    try:
        chat_id = await request.app["lobby"].start_search_and_wait(user_id)
    except Lobby.AlreadySearchingError:
        logger.error("USER %s WAS ALREADY SEARCHING", user_id)
        raise ValidationError(message="Already searching")

    if chat_id is None:
        logger.info("TO USER %s: CHAT NOT FOUND (ABORTED)", user_id)
        raise ValidationError(message="Search was aborted")

    chat_id = chat_id.hex

    logger.info("TO USER %s: SENDING CHAT %s", user_id, chat_id)

    return json_response({"chat_id": chat_id})


@operations.register("abortSearch")
@jwt_auth
async def abort_search(request: Request) -> Response:
    user_id = request["user_id"]

    try:
        request.app["lobby"].abort_search(user_id)
    except Lobby.WasNotSearchingError:
        logger.info("USER %s ABORTED CHAT SEARCH (WAS NOT SEARCHING)", user_id)
        return json_response()

    logger.info("USER %s ABORTED CHAT SEARCH", user_id)

    return json_response()


@operations.register("joinChat")
async def join_chat(request: Request) -> Response:
    with openapi_context(request) as context:
        chat_id = context.parameters.path["chat_id"]
    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        logger.error("Invalid chat_id!")
        raise ValidationError(message="Invalid chat_id")

    logger.info("SWITCHING TO WEBSOCKET...")

    # Upgrade connection to websocket
    ws = WebSocketResponse()
    try:
        await ws.prepare(request)
    except HTTPBadRequest:
        logger.error("BAD HTTP REQUEST FOR WEBSOCKET")
        raise ValidationError(message="Websocket connection is required")

    logger.info("NOW IN WEBSOCKET")

    # Obtain chat instance
    try:
        chat = request.app["chats_list"].find_chat(chat_id)
    except ChatsList.ChatNotFoundError:
        logger.error("CHAT %s NOT FOUND", chat_id)
        await ws.close(code=WSCloseCode.UNSUPPORTED_DATA, message="Chat not found".encode("utf-8"))
        return Response()

    logging.info("CHAT %s FOUND, WAITING FOR TOKEN...", chat_id)

    # Receive token from websocket
    token = await ws.receive_str()

    # Validate and obtain user_id from it
    try:
        user_id = Auth.verify(token)
    except Auth.InvalidToken:
        logger.error("INVALID JWT TOKEN: %s", token)
        await ws.close(code=WSCloseCode.UNSUPPORTED_DATA, message="Invalid JWT token".encode("utf-8"))
        return Response()

    logger.info("CONFIRMED TOKEN, IT IS USER %s, CONNECTING...", user_id)

    # Perform chatting until exited
    await chat.connect_and_stay(user_id, ws)

    return Response()


@operations.register("leaveChat")
@jwt_auth
async def leave_chat(request: Request) -> Response:
    user_id = request["user_id"]
    with openapi_context(request) as context:
        chat_id = context.parameters.path["chat_id"]
    try:
        chat_id = uuid.UUID(chat_id)
    except ValueError:
        logger.error("INVALID CHAT ID: %s", chat_id)
        raise ValidationError(message="Invalid chat_id")

    try:
        await request.app["chats_list"].close_chat(chat_id, user_id)
    except ChatsList.ChatNotFoundError:
        pass

    return json_response()


@operations.register("getPublicUserInfo")
async def get_public_user_info(request: Request) -> Response:
    with openapi_context(request) as context:
        username = context.parameters.path["username"]

    # Get profile info
    async with db.get_session(request) as session:
        user = await get_user(session, username=username)
    displayed_name = user.displayed_name

    # Send profile data to the user
    return json_response({
        'displayed_name': displayed_name,
    })


@operations.register("getAllUserInfo")
@jwt_auth
async def get_all_user_info(request: Request) -> Response:
    user_id = request['user_id']

    # Get profile data
    async with db.get_session(request) as session:
        user = await get_user(session, user_id=user_id)
    displayed_name = user.displayed_name
    username = user.username

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
    user_id = request['user_id']
    with openapi_context(request) as context:
        try:
            public_info = context.data['public']
            displayed_name = public_info['displayed_name']
            private_info = context.data['private']
            username = private_info['username']
        except KeyError:
            raise ValidationError(message="Wrong body schema")

    async with db.get_session(request) as session:
        # Obtain user
        user = await get_user(session, user_id=user_id)

        if username != user.username:
            # Prevent username conflict
            try:
                await get_user(session, username=username)
            except ValidationError:
                pass
            else:
                raise ValidationError(message="Username is taken")

        # Change profile data
        user.displayed_name = displayed_name
        user.username = username
        await session.commit()

    return json_response()


@operations.register("clearRuntime")
async def clear_runtime(request: Request) -> Response:
    chats_list = request.app["chats_list"]
    while chats_list.chats:
        await chats_list.close_chat(list(chats_list.chats.keys())[0], None)

    lobby = request.app["lobby"]
    if lobby.pending is not None:
        lobby.abort_search(lobby.pending.user_id)

    print("\n\n\n\t\tRUNTIME CLEARED\n\n\n", flush=True)
    return Response(text="RUNTIME CLEARED")


@operations.register("clearDb")
async def clear_db(request: Request) -> Response:
    async with db.get_session(request) as session:
        query = delete(db.User)
        await session.execute(query)
        await session.commit()
    print("\n\n\n\t\tDB CLEARED\n\n\n", flush=True)
    return Response(text="DB CLEARED")


async def get_user(session, **filter_kwargs):
    query = select(db.User).filter_by(**filter_kwargs)
    try:
        result = await session.execute(query)
        user = result.scalar_one()
    except NoResultFound:
        logger.error("USER IS NOT FOUND!")
        raise ValidationError(message="User not found")
    return user
