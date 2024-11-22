from typing import cast

from sqlmodel import Session, select

from user_role_group_mgr.model import User


class UserApi:
    @staticmethod
    def get_user_list(group_id: int | None,
                      db: Session) -> list[User]:
        stmt = select(User).where(User.group_id == group_id)
        return cast(list[User], db.exec(stmt).all())
