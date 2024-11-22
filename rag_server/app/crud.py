from typing import cast

from sqlmodel import Session, select

from app.model import App


def get_app_list_by_top_group_id(top_group_id: int, db: Session) -> list[App]:
    return cast(list[App], db.exec(select(App).where(App.top_group_id == top_group_id)).all())
