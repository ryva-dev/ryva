import math


class InMemoryVectorStore:
    """Simple in-memory vector store using keyword matching.
    In real use this would connect to Pinecone, Chroma, pgvector, etc."""

    def __init__(self):
        self.documents = [
            {"id": "doc1", "text": "Ryva is a framework for building agentic AI systems"},
            {"id": "doc2", "text": "dbt is a framework for data transformation and analytics"},
            {"id": "doc3", "text": "Python is a programming language used for AI and data science"},
            {"id": "doc4", "text": "Vector databases store embeddings for semantic search"},
            {"id": "doc5", "text": "Machine learning models require testing and validation"},
        ]

    def query(self, query: str, top_k: int = 5) -> list:
        query_words = set(query.lower().split())
        scored = []

        for doc in self.documents:
            doc_words = set(doc["text"].lower().split())
            overlap = len(query_words & doc_words)
            score = overlap / (len(query_words) + len(doc_words) - overlap + 1e-9)
            scored.append({
                "id": doc["id"],
                "text": doc["text"],
                "score": round(score, 4)
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def get(self, doc_id: str) -> dict | None:
        for doc in self.documents:
            if doc["id"] == doc_id:
                return doc
        return None


store = InMemoryVectorStore()


def load() -> InMemoryVectorStore:
    return store