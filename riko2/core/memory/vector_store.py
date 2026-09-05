from typing import Optional, Any, List, Dict, Tuple
import re
from riko2.core.memory.db import MemoryDB
from collections import Counter
from typing import Callable
import json
import math 


# --- VectorIndex (từ 003_vectordb.ipynb / 005_hybrid.ipynb) ---
class VectorIndex:
    def __init__(self, distance_metric: str = "cosine", embedding_fn=None):
        self.vectors: List[List[float]] = []
        self.documents: List[Dict[str, Any]] = []
        self._vector_dim: Optional[int] = None
        if distance_metric not in ["cosine", "euclidean"]:
            raise ValueError("distance_metric must be 'cosine' or 'euclidean'")
        self._distance_metric = distance_metric
        self._embedding_fn = embedding_fn

    def add_document(self, document: Dict[str, Any]):
        if not self._embedding_fn:
            raise ValueError("Embedding function not provided during initialization.")
        vector = self._embedding_fn(document["content"])
        self.add_vector(vector=vector, document=document)

    def add_documents(self, documents: List[Dict[str, Any]]):
        if not self._embedding_fn:
            raise ValueError("Embedding function not provided during initialization.")
        if not documents:
            return
        contents = [doc["content"] for doc in documents]
        vectors = self._embedding_fn(contents)
        for vector, document in zip(vectors, documents):
            self.add_vector(vector=vector, document=document)

    def search(self, query: Any, k: int = 1) -> List[Tuple[Dict[str, Any], float]]:
        if not self.vectors:
            return []

        if isinstance(query, str):
            if not self._embedding_fn:
                raise ValueError("Embedding function not provided for string query.")
            query_vector = self._embedding_fn(query)
        elif isinstance(query, list) and all(isinstance(x, (int, float)) for x in query):
            query_vector = query
        else:
            raise TypeError("Query must be either a string or a list of numbers.")

        if self._vector_dim is None or len(query_vector) != self._vector_dim:
            raise ValueError("Query vector dimension mismatch.")

        dist_func = self._cosine_distance if self._distance_metric == "cosine" else self._euclidean_distance

        distances = [(dist_func(query_vector, v), self.documents[i]) for i, v in enumerate(self.vectors)]
        distances.sort(key=lambda item: item[0])
        return [(doc, dist) for dist, doc in distances[:k]]

    def add_vector(self, vector, document: Dict[str, Any]):
        if not self.vectors:
            self._vector_dim = len(vector)
        elif len(vector) != self._vector_dim:
            raise ValueError("Inconsistent vector dimension.")
        self.vectors.append(list(vector))
        self.documents.append(document)

    def _euclidean_distance(self, vec1, vec2):
        return math.sqrt(sum((p - q) ** 2 for p, q in zip(vec1, vec2)))

    def _dot_product(self, vec1, vec2):
        return sum(p * q for p, q in zip(vec1, vec2))

    def _magnitude(self, vec):
        return math.sqrt(sum(x * x for x in vec))

    def _cosine_distance(self, vec1, vec2):
        mag1, mag2 = self._magnitude(vec1), self._magnitude(vec2)
        if mag1 == 0 and mag2 == 0:
            return 0.0
        elif mag1 == 0 or mag2 == 0:
            return 1.0
        cosine_similarity = self._dot_product(vec1, vec2) / (mag1 * mag2)
        cosine_similarity = max(-1.0, min(1.0, cosine_similarity))
        return 1.0 - cosine_similarity

    def __len__(self):
        return len(self.vectors)

# --- BM25Index (từ 004_bm25.ipynb / 005_hybrid.ipynb) ---
class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75, tokenizer: Optional[Callable[[str], List[str]]] = None):
        self.documents: List[Dict[str, Any]] = []
        self._corpus_tokens: List[List[str]] = []
        self._doc_len: List[int] = []
        self._doc_freqs: Dict[str, int] = {}
        self._avg_doc_len: float = 0.0
        self._idf: Dict[str, float] = {}
        self._index_built: bool = False
        self.k1 = k1
        self.b = b
        self._tokenizer = tokenizer if tokenizer else self._default_tokenizer

    def _default_tokenizer(self, text: str) -> List[str]:
        text = text.lower()
        tokens = re.split(r"\W+", text)
        return [token for token in tokens if token]

    def _update_stats_add(self, doc_tokens: List[str]):
        self._doc_len.append(len(doc_tokens))
        for token in set(doc_tokens):
            self._doc_freqs[token] = self._doc_freqs.get(token, 0) + 1
        self._index_built = False

    def _calculate_idf(self):
        N = len(self.documents)
        self._idf = {
            term: math.log(((N - freq + 0.5) / (freq + 0.5)) + 1)
            for term, freq in self._doc_freqs.items()
        }

    def _build_index(self):
        if not self.documents:
            self._avg_doc_len, self._idf = 0.0, {}
        else:
            self._avg_doc_len = sum(self._doc_len) / len(self.documents)
            self._calculate_idf()
        self._index_built = True

    def add_document(self, document: Dict[str, Any]):
        doc_tokens = self._tokenizer(document["content"])
        self.documents.append(document)
        self._corpus_tokens.append(doc_tokens)
        self._update_stats_add(doc_tokens)

    def add_documents(self, documents: List[Dict[str, Any]]):
        for doc in documents:
            self.add_document(doc)

    def _compute_bm25_score(self, query_tokens: List[str], doc_index: int) -> float:
        score = 0.0
        doc_term_counts = Counter(self._corpus_tokens[doc_index])
        doc_length = self._doc_len[doc_index]
        for token in query_tokens:
            if token not in self._idf:
                continue
            idf = self._idf[token]
            term_freq = doc_term_counts.get(token, 0)
            numerator = idf * term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (1 - self.b + self.b * (doc_length / self._avg_doc_len))
            score += numerator / (denominator + 1e-9)
        return score

    def search(self, query: Any, k: int = 1, score_normalization_factor: float = 0.1):
        if not self.documents or not isinstance(query, str):
            return []
        if not self._index_built:
            self._build_index()
        if self._avg_doc_len == 0:
            return []

        query_tokens = self._tokenizer(query)
        if not query_tokens:
            return []

        raw_scores = []
        for i in range(len(self.documents)):
            raw_score = self._compute_bm25_score(query_tokens, i)
            if raw_score > 1e-9:
                raw_scores.append((raw_score, self.documents[i]))
        raw_scores.sort(key=lambda item: item[0], reverse=True)

        normalized = [
            (doc, math.exp(-score_normalization_factor * raw_score))
            for raw_score, doc in raw_scores[:k]
        ]
        normalized.sort(key=lambda item: item[1])
        return normalized

    def __len__(self):
        return len(self.documents)

# --- Retriever (từ 005_hybrid.ipynb) — ghép nhiều index bằng Reciprocal Rank Fusion ---
class Retriever:
    def __init__(self, *indexes):
        if len(indexes) == 0:
            raise ValueError("At least one index must be provided")
        self._indexes = list(indexes)

    def add_document(self, document: Dict[str, Any]):
        for index in self._indexes:
            index.add_document(document)

    def add_documents(self, documents: List[Dict[str, Any]]):
        for index in self._indexes:
            index.add_documents(documents)

    def search(self, query_text: str, k: int = 1, k_rrf: int = 60):
        all_results = [index.search(query_text, k=k * 5) for index in self._indexes]

        doc_ranks = {}
        for idx, results in enumerate(all_results):
            for rank, (doc, _) in enumerate(results):
                doc_id = id(doc)
                if doc_id not in doc_ranks:
                    doc_ranks[doc_id] = {"doc_obj": doc, "ranks": [float("inf")] * len(self._indexes)}
                doc_ranks[doc_id]["ranks"][idx] = rank + 1

        def calc_rrf_score(ranks):
            return sum(1.0 / (k_rrf + r) for r in ranks if r != float("inf"))

        scored = [(r["doc_obj"], calc_rrf_score(r["ranks"])) for r in doc_ranks.values()]
        scored = [(doc, score) for doc, score in scored if score > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

# --- Retriever(vector_index, bm25_index) + đồng bộ với SQLite ---
class PersistentHybridStore:
    """Bọc Retriever(vector_index, bm25_index) + đồng bộ với SQLite để không re-embed mỗi lần boot."""
    def __init__(self, db: MemoryDB, embedder):
        self.db = db
        self.embedder = embedder
        self.vector_index = VectorIndex(embedding_fn=embedder.embed)
        self.bm25_index = BM25Index()
        self.retriever = Retriever(self.vector_index, self.bm25_index)
        self._load_from_db()

    def _load_from_db(self):
        rows = self.db.get_all_memory_facts()  # [{id, content, ts, session_id, vector_json}, ...]
        for row in rows:
            doc = {"content": row["content"], "ts": row["ts"], "session_id": row["session_id"]}
            self.vector_index.add_vector(vector=json.loads(row["vector_json"]), document=doc)
            self.bm25_index.add_document(doc)

    def add_fact(self, content: str, session_id: int, ts: float):
        vector = self.embedder.embed(content)
        doc = {"content": content, "ts": ts, "session_id": session_id}
        self.vector_index.add_vector(vector=vector, document=doc)
        self.bm25_index.add_document(doc)
        self.db.insert_memory_fact(content, ts, session_id, json.dumps(vector))

    def search(self, query_text: str, k: int = 5):
        return self.retriever.search(query_text, k=k)


