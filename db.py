import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql.asyncpg import UUID
import aiohttp_sqlalchemy as ahsa


metadata = sa.MetaData()
Base = orm.declarative_base(metadata=metadata)


class User(Base):
    __tablename__ = "user"
    user_id = sa.Column(UUID(as_uuid=True), primary_key=True)
    username = sa.Column(sa.String, unique=True)
    password = sa.Column(sa.String, nullable=False)
    displayed_name = sa.Column(sa.String, nullable=True)


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
