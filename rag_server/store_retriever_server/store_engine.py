import numpy as np
from milvus_model.dense.sentence_transformer import SentenceTransformerEmbeddingFunction
from pydantic import BaseModel
from pymilvus import MilvusClient, FieldSchema, DataType, CollectionSchema

from celery_task.model import send_process_notify, ToVectorStoreNotify
from config.config import config
from store_retriever_server.model import SearchResult

sentence_transformer_ef: SentenceTransformerEmbeddingFunction | None = None


class StoreEngine(BaseModel):
    name: str
    client: MilvusClient | None = None
    notify_url: str = config.accept_nodify_url
    embedding_model_name_or_path: str = config.embedding_model_name_or_path

    def __init__(self, name):
        super().__init__(name=name, client=MilvusClient(config.milvus_uri))

    def reset_store(self):
        if self.client.has_collection(collection_name=self.name):
            self.client.drop_collection(collection_name=self.name)

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=8192, description="text"),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=384, description="vector"),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64, description="source doc id")
        ]
        schema = CollectionSchema(fields=fields, auto_id=True, enable_dynamic_field=True)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(field_name="vector",
                               metric_type="COSINE",
                               index_type="FLAT")

        self.client.create_collection(collection_name=self.name,
                                      schema=schema,
                                      index_params=index_params)

    def delete_store(self):
        self.client.drop_collection(collection_name=self.name)

    def embed_doc(self, texts: list[str]) -> list[np.array]:
        global sentence_transformer_ef
        if sentence_transformer_ef is None:
            sentence_transformer_ef = SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model_name_or_path,
                local_files_only=self.embedding_model_name_or_path.startswith('/'),
                device='cpu')
        return sentence_transformer_ef.encode_documents(texts)

    def embed_query(self, query: str) -> np.array:
        global sentence_transformer_ef
        if sentence_transformer_ef is None:
            sentence_transformer_ef = SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model_name_or_path,
                local_files_only=self.embedding_model_name_or_path.startswith('/'),
                device='cpu')
        return sentence_transformer_ef.encode_queries([query])[0]

    def add_doc(self, texts: list[str], doc_id: str):
        # delete old docs by source doc id
        self.delete_doc(doc_id)
        send_process_notify(self.notify_url, ToVectorStoreNotify, doc_id, 10)

        vectors = self.embed_doc(texts)
        send_process_notify(self.notify_url, ToVectorStoreNotify, doc_id, 60)
        data = [dict(text=text, vector=vector, doc_id=doc_id) for text, vector in zip(texts, vectors)]
        self.client.insert(collection_name=self.name, data=data)
        send_process_notify(self.notify_url, ToVectorStoreNotify, doc_id, 100)

    def delete_doc(self, doc_id: str):
        self.client.delete(collection_name=self.name, filter=f"doc_id == '{doc_id}'")

    def search(self, query: str, limit: int = 3) -> list[SearchResult]:
        res = self.client.search(
            collection_name=self.name,
            data=[self.embed_query(query)],
            limit=limit,
            output_fields=["text", "doc_id"],
            # search_params={"metric_type": "IP", "params": {}}  # Search parameters
        )

        return [SearchResult(id=item['id'],
                             text=item['entity']['text'],
                             distance=item['distance'],
                             doc_id=item['entity']['doc_id']) for item in res[0]]

    class Config:
        arbitrary_types_allowed = True
