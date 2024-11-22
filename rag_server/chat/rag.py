from auto_flow.core.llm.openai.openai_llm import OpenAILLM

from chat.model import ChatRecord
from store_retriever_server.api import search
from store_retriever_server.model import SearchRequest, SearchResult


def retrieve_by_chat_records(records: list[ChatRecord], kb_ids: list[str]) -> list[SearchResult]:
    prompt_template = """
        请根据以下历史对话记录，总结出用户要查询的关键信息，并生成一个简洁的查询文本。
        对话记录的格式，user 代表用户，assistant 代表 AI 对用户的回复。
        历史对话记录：
        {history}

        要求：
        - 从对话中提取最相关的问题或关键信息
        - 忽略无关内容
        - 输出应简明扼要，适合用于向量数据库的查询

        总结的查询文本：
        """
    # 取最近十条对话记录
    records = [f"{record.message['role']}: {record.message['content']}"
               for record in records[max(0, len(records) - 20):]]

    search_results: list[SearchResult] = []
    if kb_ids:
        llm = OpenAILLM(model="gpt-4o",
                        base_url="https://api.chatfire.cn/v1",
                        api_key="sk-r7S6MM5xPgguyi30fNwKgtQ0TQ21iKiyMnn20nQLSJsLC1w2")
        query = llm.chat(prompt_template.format(history='\n'.join(records))).messages[0].content
        for kb_id in kb_ids:
            request = SearchRequest(kb_id=kb_id, query=query, limit=3)
            search_results.extend(search(request))

    search_results.sort(key=lambda x: x.distance)
    return search_results


def augment_query_by_kb_context(query: str, context: list[str]) -> str:
    prompt_template = """
    你是一名专家。以下是用户的提问，以及从知识库中检索到的一些相关上下文信息。请结合这些上下文信息，为用户提供全面且有帮助的回答。

    **用户问题**：
    {query}

    **上下文信息**：
    {context}

    请根据上述信息提供准确且相关的答案。如果你需要更多信息，或者有其他问题，请随时提问。
    """
    return prompt_template.format(query=query, context='\n'.join(context))
