from sqlalchemy import text
from sqlmodel import create_engine, Session

from config.config import config
from sqlmodel import SQLModel
import user_role_group_mgr.model  # import model before create!
import file_mgr.model
import chat.model


engine = create_engine(config.sql_url, echo=False)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    # only for sqlite
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))


def get_session():
    with Session(engine) as session:
        yield session
