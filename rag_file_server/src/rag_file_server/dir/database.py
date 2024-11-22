from sqlalchemy import text, DDL
from sqlmodel import create_engine

from rag_file_server.config.config import config
from .model import SQLModel

engine = create_engine(config.dir.sql_url, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

    # 创建 filenode 的 当 parent_id == NULL, name 必须唯一的 约束
    with engine.begin() as connection:
        # 检查触发器是否存在
        result = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='unique_name_when_parent_null';")).fetchone()

        # 如果触发器不存在，则创建它
        if result is None:
            connection.execute(DDL("""
                CREATE TRIGGER unique_name_when_parent_null
                BEFORE INSERT ON filenode
                FOR EACH ROW
                WHEN NEW.parent_id IS NULL
                BEGIN
                    SELECT
                        CASE
                            WHEN (SELECT COUNT(*) FROM filenode WHERE name = NEW.name AND parent_id IS NULL) > 0
                            THEN RAISE(ABORT, 'Name must be unique when parent_id is NULL')
                        END;
                END;
                """))

        update_trigger_check_query = text(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='unique_name_update_when_parent_null';")
        update_result = connection.execute(update_trigger_check_query).fetchone()

        if update_result is None:
            connection.execute(DDL("""
                CREATE TRIGGER unique_name_update_when_parent_null
                BEFORE UPDATE ON filenode
                FOR EACH ROW
                WHEN NEW.parent_id IS NULL
                BEGIN
                    SELECT
                        CASE
                            WHEN (SELECT COUNT(*) FROM filenode WHERE name = NEW.name AND parent_id IS NULL AND id != OLD.id) > 0
                            THEN RAISE(ABORT, 'Name must be unique when parent_id is NULL during update')
                        END;
                END;
                """))
