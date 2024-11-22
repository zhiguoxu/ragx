from sqlalchemy import delete
from sqlmodel import Session

from chat.model import ChatSession


def delete_session_by_app_id(app_id: str, db: Session):
    db.exec(delete(ChatSession).where(ChatSession.app_id == app_id))
    db.commit()
