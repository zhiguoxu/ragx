from requests import Response
from rag_file_server.error_code import raise_exception


def check_response(response: Response):
    if not response.ok:
        try:
            desc = response.json().get('detail')
        except Exception as e:
            desc = response.text
        raise_exception(response.status_code, desc)
