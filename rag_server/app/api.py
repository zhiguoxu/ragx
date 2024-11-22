import time
from typing import cast
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.crud import get_app_list_by_top_group_id
from app.model import App
from chat.crud import delete_session_by_app_id
from db.database import get_session
from user_role_group_mgr.auth import get_current_user
from user_role_group_mgr.model import User
from util import check_permission

router = APIRouter(prefix="/app", tags=["app"])


@router.get('/list', response_model=list[App])
def get_app_list(top_group_id: int,
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_session)) -> list[App]:
    check_permission(top_group_id, user)
    return get_app_list_by_top_group_id(top_group_id, db)


@router.put('', response_model=App)
def add_app(app: App,
            user: User = Depends(get_current_user),
            db: Session = Depends(get_session)) -> App:
    check_permission(App.top_group_id, user)

    app.id = None
    app.create_user_id = user.id
    app.create_time = time.time()
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.post('')
def update_app(app: App,
               user: User = Depends(get_current_user),
               db: Session = Depends(get_session)):
    check_permission(app.top_group_id, user)
    db_app = db.get(App, app.id)
    db_app.sqlmodel_update(
        app.model_dump(exclude={'create_user_id', 'create_time', 'top_group_id'}, exclude_unset=True))
    db.add(db_app)
    db.commit()


@router.delete('/{app_id:path}')
def delete_app(app_id: str,
               user: User = Depends(get_current_user),
               db: Session = Depends(get_session)):
    app = db.get(App, app_id)
    check_permission(app.top_group_id, user)
    db.delete(app)
    delete_session_by_app_id(app_id, db)
    db.commit()


@router.get('/{app_id:path}')
def get_app_by_id(app_id: str,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_session)) -> dict:
    app = cast(App, db.get_one(App, app_id))
    check_permission(app.top_group_id, user)
    return app.model_dump()
