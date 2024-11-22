from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from db.database import get_session
from user_role_group_mgr.auth import get_current_user
from user_role_group_mgr.model import User, Role, Group, Status

router = APIRouter(prefix="/data", tags=["data"])


class KvData(BaseModel):
    key: str | int
    value: str


@router.get("/kv_list/{name:path}", response_model=list[KvData])
def get_kv_list(name: str,
                db: Session = Depends(get_session),
                user: User = Depends(get_current_user)) -> list[KvData]:
    if name == 'Role':
        return [KvData(key=role.id, value=role.name) for role in db.exec(select(Role))]

    if name == 'TopGroup':
        stmt = select(Group).where((Group.parent_id == None) & (Group.status != Status.DELETED))
        return [KvData(key=group.id, value=group.name) for group in db.exec(stmt)]

    if name == 'LLM':
        return [KvData(key=1, value='gpt-4o')]

    return []
