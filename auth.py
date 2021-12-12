import jwt
import uuid
import aiohttp.web
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from werkzeug.security import generate_password_hash

import db


class Auth:
    JWT_SECRET = "CHEEVO???"

    class UsernameIsTakenError(Exception):
        pass

    class WrongCredentials(Exception):
        pass

    class InvalidToken(Exception):
        pass

    @staticmethod
    async def signup(session, username, password, displayed_name):
        """ Registers user in the DB and performs login (returning token) """
        # Is the username free?
        if (await session.execute(select(db.User).filter_by(username=username))).first():
            raise Auth.UsernameIsTakenError()

        # If yes, create new user
        password = generate_password_hash(password)
        new_user = db.User(username=username,
                           password=password,
                           displayed_name=displayed_name)
        session.add(new_user)

        # And perform login
        return await Auth.login(session, username, password)

    @staticmethod
    async def login(session, username, password):
        """ Generates login JWT Bearer token"""
        # Do the credentials match?
        try:
            user = (await session.execute(select(db.User).filter_by(username=username, password=password))).scalar_one()
        except NoResultFound:
            raise Auth.WrongCredentials()

        # If yes, encode user_id into JWT token and send it to the client
        jwt_payload = {
            'user_id': user.user_id.hex
        }
        return jwt.encode(jwt_payload, Auth.JWT_SECRET, algorithm="HS256")

    @staticmethod
    def verify(jwt_token):
        """ Decodes JWT Bearer token and returns user_id from its payload """
        try:
            jwt_payload = jwt.decode(jwt_token, Auth.JWT_SECRET, algorithms=["HS256"])
            user_id = uuid.UUID(jwt_payload['user_id'])
        except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
            raise Auth.InvalidToken() from exc
        return user_id


def authorize(handler):
    """ Wrapper for request handlers, processes JWS Bearer token and adds user_id to the request dict """
    async def wrapper(request):
        try:
            jwt_token = request.headers["Authorization"].split()[1]
            user_id = Auth.verify(jwt_token)
        except (KeyError, IndexError, Auth.InvalidToken):
            raise aiohttp.web.HTTPUnauthorized
        request["user_id"] = user_id
        return await handler(request)
    return wrapper
