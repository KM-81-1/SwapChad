import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql.asyncpg import UUID
import aiohttp_sqlalchemy as ahsa


metadata = sa.MetaData()
Base = orm.declarative_base(metadata=metadata)


class User(Base):
    __tablename__ = "user"
    user_id = sa.Column(UUID(as_uuid=True), primary_key=True)
    username = sa.Column(sa.String, unique=True, nullable=False)
    password = sa.Column(sa.String, nullable=False)
    displayed_name = sa.Column(sa.String, nullable=True)
    saved_chats = orm.relationship("SavedChat")


class SavedChat(Base):
    __tablename__ = "saved_chat"
    chat_id = sa.Column(UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey('user.user_id'), primary_key=True)
    offset = sa.Column(sa.Integer, nullable=False, default=0)
    title = sa.Column(sa.String, nullable=True)


class Message(Base):
    __tablename__ = "message"
    chat_id = sa.Column(UUID(as_uuid=True), primary_key=True)
    message_id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey('user.user_id'), nullable=False)
    text = sa.Column(sa.String, nullable=False)


async def connect(app, url):
    """ Connects to the database """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    ahsa.setup(app, [
        ahsa.bind(url),
    ])
    await ahsa.init_db(app, metadata=metadata)


def get_session(request):
    """ Obtains session from aiohttp_sqlalchemy """
    return ahsa.get_session(request)
