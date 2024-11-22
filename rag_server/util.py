from requests import Response
from error_code import raise_exception, ErrorCode
from user_role_group_mgr.model import User


def check_response(response: Response):
    if not response.ok:
        try:
            desc = response.json().get('detail')
        except Exception as e:
            desc = response.text
        raise_exception(response.status_code, desc)


def check_permission(top_group_id: int, user: User):
    if user.level > 2 and user.top_group_id != top_group_id:
        raise_exception(ErrorCode.NO_PERMISSION)
