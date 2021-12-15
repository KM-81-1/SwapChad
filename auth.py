import logging
import jwt
import uuid
from rororo.openapi import BasicSecurityError
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
    
import db

logger = logging.getLogger(__name__)


class Auth:
    JWT_SECRET = "SwApChAd"

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
            logger.error("USERNAME %s IS TAKEN", username)
            raise Auth.UsernameIsTakenError()

        # If yes, create new user
        new_user = db.User(user_id=uuid.uuid4(),
                           username=username,
                           password=password,
                           displayed_name=displayed_name)
        session.add(new_user)
        await session.commit()

        # And perform login
        return await Auth.login(session, username, password)

    @staticmethod
    async def login(session, username, password):
        """ Generates login JWT Bearer token"""
        # Do the credentials match?
        try:
            user = (await session.execute(select(db.User).filter_by(username=username))).scalar_one()
        except NoResultFound:
            logger.error("WRONG CREDENTIALS (NO SUCH USER)")
            raise Auth.WrongCredentials()
        if password != user.password:
            logger.error("WRONG CREDENTIALS (PASSWORDS MISMATCH)")
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
            logger.error("INVALID TOKEN: %s", jwt_token)
            raise Auth.InvalidToken() from exc
        return user_id


def jwt_auth(handler):
    """ Wrapper for request handlers, validates JWS Bearer token and adds extracted user_id to the request dict """
    async def wrapper(request):
        try:
            jwt_token = request.headers["Authorization"].split()[1]
        except (KeyError, IndexError):
            logger.error("MISSING JWT BEARER TOKEN IN AUTHORIZATION HEADER")
            raise BasicSecurityError(message="Missing JWT Bearer token")

        try:
            user_id = Auth.verify(jwt_token)
        except Auth.InvalidToken:
            raise BasicSecurityError(message="Invalid JWT token")

        request["user_id"] = user_id

        logger.info("AUTHENTICATED USER %s VIA TOKEN", user_id)

        return await handler(request)
    return wrapper
