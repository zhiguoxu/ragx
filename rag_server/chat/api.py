import json
import time
from typing import Iterator, cast

from auto_flow.core.messages.chat_message import ChatMessage, ChatMessageChunk, Role
from auto_flow.core.utils.utils import add
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from starlette.responses import StreamingResponse

from app.model import App
from chat.model import ChatRequest, ChatSession, ChatRecord, ChatSessionType
from chat.rag import retrieve_by_chat_records, augment_query_by_kb_context
from db.database import get_session
from user_role_group_mgr.auth import get_current_user
from user_role_group_mgr.model import User

router = APIRouter(prefix="/chat", tags=["chat"])


def add_session(app_id: str,
                user_id: int,
                name: str,
                session_type: ChatSessionType,
                db: Session):
    session = ChatSession(app_id=app_id, user_id=user_id, name=name, type=session_type)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/chat")
def chat(request: ChatRequest,
         user: User = Depends(get_current_user),
         db: Session = Depends(get_session)):
    if request.session_id is None:
        chat_session = add_session(request.app_id, user.id, request.input_text, ChatSessionType.NORMAL, db)
    else:
        chat_session = db.get(ChatSession, request.session_id)

    # 准备上下文
    app = cast(App, db.get_one(App, request.app_id))
    if app.kb_ids:
        search_result = retrieve_by_chat_records(chat_session.records, app.kb_ids)
        kb_context = [result.text for result in search_result]
        augmented_query = augment_query_by_kb_context(request.input_text, kb_context)
    else:
        augmented_query = None

    # 准备历史聊天记录
    user_message = ChatMessage(role=Role.USER, content=request.input_text)
    user_record = ChatRecord(session_id=chat_session.id, message=user_message.model_dump())
    chat_session.records.sort(key=lambda x: x.timestamp)

    def to_response_stream() -> Iterator[str]:
        if not request.session_id:
            yield json.dumps({'session': chat_session.model_dump()}) + "\r\n" * 10

        message_cache: ChatMessageChunk | None = None
        from auto_flow.core.llm.openai.openai_llm import OpenAILLM

        messages = [ChatMessage.model_validate(record.message) for record in chat_session.records]

        messages.append(ChatMessage(role=Role.USER, content=augmented_query or request.input_text))
        llm = OpenAILLM(model="gpt-4o",
                        base_url="https://api.chatfire.cn/v1",
                        api_key="sk-r7S6MM5xPgguyi30fNwKgtQ0TQ21iKiyMnn20nQLSJsLC1w2")
        result = llm.stream_chat(messages, **app.llm_config)

        try:
            for chunk, _ in result.message_stream:
                message_chunk = chunk.model_dump()
                message_cache = add(message_cache, chunk)
                yield json.dumps({'message_chunk': message_chunk,
                                  'timestamp': time.time()}) + "\r\n" * 10
                # 如果浏览器刷新页面，流被中断后，后面的代码都不会执行
        except GeneratorExit:
            # 捕获生成器关闭的异常，当客户端断开时会触发
            print("Stream was closed due to client disconnect")
        except Exception as e:
            print(f"Unexpected error: {e}")

        assert message_cache
        ai_record = ChatRecord(session_id=chat_session.id,
                               message=message_cache.to_message().model_dump())

        db.add_all([user_record, ai_record])
        db.commit()

    return StreamingResponse(to_response_stream(), media_type="application/json")


@router.get("/session_by_id")
def get_session_by_id(session_id: str, db: Session = Depends(get_session)) -> dict:
    session = cast(ChatSession, db.get_one(ChatSession, session_id))
    session.records.sort(key=lambda x: x.timestamp)
    return session.model_dump()  # 因为没有办法返回 records，只能用自定义的 model_dump 来实现。


@router.get("/test_session_by_app")
def get_test_session_by_app(app_id: str,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_session)) -> ChatSession:
    stmt = select(ChatSession).where(ChatSession.app_id == app_id,
                                     ChatSession.user_id == user.id,
                                     ChatSession.type == ChatSessionType.TEST)
    session = cast(ChatSession, db.exec(stmt).first())
    if session is None:
        session = add_session(app_id, user.id, "测试会话", ChatSessionType.TEST, db)
    return session


@router.post("/session/reset")
def reset_session(session_id: str, db: Session = Depends(get_session)):
    session = db.get_one(ChatSession, session_id)
    session.records = []
    db.add(session)
    db.commit()


@router.delete("/session")
def delete_session(session_id: str, db: Session = Depends(get_session)):
    session = db.get_one(ChatSession, session_id)
    db.delete(session)
    db.commit()


@router.get("/session_list")
def get_session_list(app_id: str, db: Session = Depends(get_session)):
    stmt = select(ChatSession).where(ChatSession.app_id == app_id)
    return cast(list[ChatSession], db.exec(stmt).all())


@router.post("/session")
def update_session(session: ChatSession, db: Session = Depends(get_session)):
    session_po = db.get_one(ChatSession, session.id)
    # session 只有 name 可以修改
    session_po.name = session.name
    db.add(session_po)
    db.commit()
