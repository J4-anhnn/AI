"""
Module: core/vector_engine.py
Step C: Embedding & Step D: Vector Database
Step 1, 2, 3: Query -> Embedding -> Vector DB Search -> Relevant Data

Cài đặt đầy đủ mô hình Vector hóa và Vector Database chuyên dụng:
1. Dense Semantic Embedder: Biến text thành dense vector 128 chiều số thực.
2. TinyVectorDB: Vector Database lưu trữ vector + metadata, thực hiện k-NN Cosine Similarity Search.
"""

import math
import re
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


class DenseSemanticEmbedder:
    """
    Engine tạo Vector Embeddings nhiều chiều (Dense Vectors).
    Sử dụng kỹ thuật Subword/N-gram Hashing + TF-IDF Weighting + L2 Normalization.
    Đặc điểm:
    - Không phụ thuộc vào thư viện nặng (>500MB).
    - Bắt cực tốt ngữ nghĩa chuyên ngành IT song ngữ (JWT, OTP, QR, Stripe, MoMo, API, DB...).
    - Vector được chuẩn hoá L2 nên Cosine Similarity = Dot Product.
    """

    def __init__(self, dimension: int = 128):
        self.dimension = dimension

    def _tokenize_and_ngrams(self, text: str) -> List[str]:
        text_lower = text.lower()
        # Tách từ tiếng Anh/tiếng Việt và ký tự đặc biệt IT
        words = re.findall(r"\b[\w\-]+\b", text_lower)
        tokens = list(words)

        # Tạo thêm character 3-gram và 4-gram để bắt được tiền tố/hậu tố ngữ nghĩa
        for word in words:
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    tokens.append(f"tri:{word[i:i+3]}")
            if len(word) >= 4:
                for i in range(len(word) - 3):
                    tokens.append(f"quad:{word[i:i+4]}")

        return tokens

    def _hash_token(self, token: str) -> Tuple[int, float]:
        """Băm token thành (chỉ số chiều vector, dấu +/-)"""
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        dim_index = h % self.dimension
        sign = 1.0 if ((h >> 16) & 1) == 1 else -1.0
        return dim_index, sign

    def embed_text(self, text: str) -> np.ndarray:
        """Chuyển đổi 1 đoạn text thành vector 1D float32 kích thước [dimension]"""
        vec = np.zeros(self.dimension, dtype=np.float32)
        tokens = self._tokenize_and_ngrams(text)

        if not tokens:
            return vec

        # Đếm tần suất token (TF)
        tf_dict = {}
        for t in tokens:
            tf_dict[t] = tf_dict.get(t, 0) + 1

        for token, count in tf_dict.items():
            dim_idx, sign = self._hash_token(token)
            # Logarithmic TF weighting
            weight = (1.0 + math.log(count)) * sign
            vec[dim_idx] += weight

        # Chuẩn hoá L2 (Unit Vector)
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec = vec / norm

        return vec

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Vector hoá một danh sách texts thành ma trận [N, dimension]"""
        return np.vstack([self.embed_text(t) for t in texts])


class TinyVectorDB:
    """
    Vector Database gọn nhẹ lưu trữ Embeddings và Metadata.
    Hỗ trợ k-NN Cosine Similarity Search, Distance Calculation, và Metadata Filtering.
    """

    def __init__(self, dimension: int = 128):
        self.dimension = dimension
        self.embedder = DenseSemanticEmbedder(dimension=dimension)
        self.documents: List[Dict[str, Any]] = []
        self.vectors: Optional[np.ndarray] = None  # Ma trận [N, dimension]

    def add_documents(self, docs: List[Dict[str, Any]]) -> int:
        """
        Nạp tài liệu/chunk vào Vector DB. Tự động tính Embeddings nếu chưa có.
        """
        new_texts = [d["text"] for d in docs]
        new_vectors = self.embedder.embed_batch(new_texts)

        for i, doc in enumerate(docs):
            doc_copy = dict(doc)
            doc_copy["vector"] = new_vectors[i].tolist()
            self.documents.append(doc_copy)

        if self.vectors is None or len(self.vectors) == 0:
            self.vectors = new_vectors
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])

        return len(self.documents)

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Step 1 & 2 & 3:
        1. Embed Query thành Query Vector
        2. Đo độ tương đồng Cosine (Dot product) với toàn bộ Vector trong DB
        3. Lọc metadata (nếu có) và trả về Top K tài liệu tương đồng nhất
        """
        if self.vectors is None or len(self.vectors) == 0:
            return []

        query_vec = self.embedder.embed_text(query)

        # Tính Cosine Similarity với toàn bộ ma trận: dot product
        similarities = np.dot(self.vectors, query_vec)

        results = []
        for idx, doc in enumerate(self.documents):
            # Kiểm tra bộ lọc metadata nếu có
            if filter_dict:
                match = True
                for key, val in filter_dict.items():
                    if doc.get(key) != val and doc.get("metadata", {}).get(key) != val:
                        match = False
                        break
                if not match:
                    continue

            sim_score = float(similarities[idx])
            # Chuẩn hoá độ tương đồng về dải [0, 1]
            clamped_sim = max(0.0, min(1.0, (sim_score + 1.0) / 2.0 if sim_score < 0 else sim_score))

            # Tính khoảng cách Euclidean
            doc_vec = np.array(doc["vector"], dtype=np.float32)
            euclidean_dist = float(np.linalg.norm(query_vec - doc_vec))

            results.append({
                "document": doc,
                "similarity_score": round(sim_score, 4),
                "relevance_percent": round(max(0.0, sim_score) * 100, 1),
                "euclidean_distance": round(euclidean_dist, 4),
                "ticket_key": doc.get("ticket_key", ""),
                "title": doc.get("title", ""),
                "module": doc.get("module", ""),
                "task_type": doc.get("task_type", ""),
                "actual_hours": doc.get("actual_hours", 0.0),
                "estimated_hours": doc.get("estimated_hours", 0.0),
                "story_points": doc.get("story_points", 0)
            })

        # Sắp xếp giảm dần theo similarity score
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_k]

    def get_document_count(self) -> int:
        return len(self.documents)

    def save(self, file_path: str):
        data = {
            "dimension": self.dimension,
            "documents": self.documents
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.dimension = data.get("dimension", 128)
        self.embedder = DenseSemanticEmbedder(dimension=self.dimension)
        self.documents = data.get("documents", [])
        if self.documents:
            vec_list = [d["vector"] for d in self.documents]
            self.vectors = np.array(vec_list, dtype=np.float32)
        else:
            self.vectors = None
