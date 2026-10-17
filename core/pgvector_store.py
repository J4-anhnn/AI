"""
Module: core/pgvector_store.py
Enterprise PostgreSQL + pgvector Integration
Cung cấp bộ lưu trữ Vector chuyên nghiệp (Persistent Vector Store)
sử dụng PostgreSQL 14+ và extension pgvector với chỉ mục HNSW (Hierarchical Navigable Small World).
"""

import os
import json
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from pgvector.psycopg2 import register_vector
from core.vector_engine import DenseSemanticEmbedder


class PgVectorStore:
    """
    Quản lý kết nối và thao tác với PostgreSQL + pgvector:
    - Lưu trữ Ticket lịch sử kèm Vector Embedding 128 chiều.
    - HNSW Cosine Index cho truy vấn dưới 1ms với hàng triệu vectors.
    - Truy vấn k-NN Cosine Similarity: 1 - (embedding <=> query_vector::vector)
    """

    DEFAULT_DSN = os.environ.get(
        "DATABASE_URL",
        "postgresql://localhost:5432/ai_vector_rag"
    )

    def __init__(self, dsn: str = None, dimension: int = 128):
        self.dsn = dsn or self.DEFAULT_DSN
        self.dimension = dimension
        self.embedder = DenseSemanticEmbedder(dimension=dimension)
        self.is_connected = False
        self._init_db()

    def _get_connection(self):
        conn = psycopg2.connect(self.dsn)
        register_vector(conn)
        return conn

    def _init_db(self):
        """Khởi tạo extension vector, bảng dữ liệu và index HNSW"""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Kích hoạt extension vector
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                    # 2. Bảng historical_tasks (Kho dữ liệu lịch sử)
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS historical_tasks (
                            id SERIAL PRIMARY KEY,
                            ticket_key VARCHAR(50) UNIQUE NOT NULL,
                            title TEXT NOT NULL,
                            module VARCHAR(100) NOT NULL,
                            task_type VARCHAR(50) NOT NULL,
                            tech_stack TEXT,
                            description TEXT,
                            estimated_hours NUMERIC(6, 2) DEFAULT 0,
                            actual_hours NUMERIC(6, 2) DEFAULT 0,
                            story_points INT DEFAULT 0,
                            priority VARCHAR(30) DEFAULT 'Medium',
                            embedding vector({self.dimension}),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                    """)

                    # 3. Tạo HNSW Index cho Cosine Distance (<=>)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_historical_tasks_hnsw_cosine 
                        ON historical_tasks USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64);
                    """)

                    # 4. Bảng dev_backlog_runs (Lưu vết các đợt phân tích Excel của Dev)
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS dev_backlog_history (
                            id SERIAL PRIMARY KEY,
                            raw_title TEXT NOT NULL,
                            standardized_title TEXT,
                            module VARCHAR(100),
                            task_type VARCHAR(50),
                            tech_stack TEXT,
                            estimated_hours NUMERIC(6, 2),
                            story_points INT,
                            flag_status VARCHAR(50),
                            flag_reason TEXT,
                            matched_ticket_key VARCHAR(50),
                            similarity_score NUMERIC(6, 4),
                            is_approved BOOLEAN DEFAULT FALSE,
                            imported_platform VARCHAR(30),
                            jira_ado_key VARCHAR(50),
                            embedding vector({self.dimension}),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
            self.is_connected = True
            print(f"[PgVectorStore] Đã kết nối thành công PostgreSQL ({self.dsn}) và khởi tạo HNSW index.")
        except Exception as e:
            self.is_connected = False
            print(f"[PgVectorStore Warning] Không thể kết nối PostgreSQL: {e}")

    def add_historical_tasks(self, tasks: List[Dict[str, Any]], vectors: np.ndarray) -> int:
        """
        Nạp danh sách ticket lịch sử và vector embedding vào PostgreSQL
        """
        if not self.is_connected or len(tasks) == 0:
            return 0

        inserted_count = 0
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    for i, t in enumerate(tasks):
                        vec = vectors[i].tolist() if isinstance(vectors[i], np.ndarray) else vectors[i]
                        cur.execute("""
                            INSERT INTO historical_tasks (
                                ticket_key, title, module, task_type, tech_stack,
                                description, estimated_hours, actual_hours,
                                story_points, priority, embedding
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ticket_key) DO UPDATE SET
                                title = EXCLUDED.title,
                                module = EXCLUDED.module,
                                task_type = EXCLUDED.task_type,
                                tech_stack = EXCLUDED.tech_stack,
                                description = EXCLUDED.description,
                                actual_hours = EXCLUDED.actual_hours,
                                story_points = EXCLUDED.story_points,
                                embedding = EXCLUDED.embedding;
                        """, (
                            t.get("ticket_key", f"PROJ-{i+100}"),
                            t.get("title", ""),
                            t.get("module", "General"),
                            t.get("task_type", "Backend"),
                            t.get("tech_stack", ""),
                            t.get("description", ""),
                            float(t.get("estimated_hours", 0)),
                            float(t.get("actual_hours", 0)),
                            int(t.get("story_points", 0)),
                            t.get("priority", "Medium"),
                            vec
                        ))
                        inserted_count += 1
                    conn.commit()
            return inserted_count
        except Exception as e:
            print(f"[PgVectorStore Error] Lỗi khi nạp tasks vào Postgres: {e}")
            return 0

    def search_similar_tasks(
        self,
        query_vector: np.ndarray,
        top_k: int = 3,
        min_similarity: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm k-NN Cosine Similarity bằng toán tử pgvector (<=>)
        Cosine Distance d = embedding <=> query_vector
        Cosine Similarity = 1 - d
        """
        if not self.is_connected:
            return []

        vec_list = query_vector.tolist() if isinstance(query_vector, np.ndarray) else query_vector
        results = []

        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Toán tử <=> trong pgvector tính Cosine Distance
                    query = """
                        SELECT 
                            ticket_key,
                            title,
                            module,
                            task_type,
                            tech_stack,
                            description,
                            actual_hours,
                            story_points,
                            priority,
                            (1 - (embedding <=> %s::vector)) AS similarity_score
                        FROM historical_tasks
                        WHERE (1 - (embedding <=> %s::vector)) >= %s
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT %s;
                    """
                    cur.execute(query, (vec_list, vec_list, min_similarity, vec_list, top_k))
                    rows = cur.fetchall()

                    for r in rows:
                        results.append({
                            "ticket_key": r["ticket_key"],
                            "title": r["title"],
                            "module": r["module"],
                            "task_type": r["task_type"],
                            "tech_stack": r["tech_stack"],
                            "description": r["description"],
                            "actual_hours": float(r["actual_hours"]),
                            "story_points": int(r["story_points"]),
                            "similarity_score": round(float(r["similarity_score"]), 4),
                            "similarity_percent": f"{round(float(r['similarity_score']) * 100, 1)}%"
                        })
            return results
        except Exception as e:
            print(f"[PgVectorStore Search Error] Lỗi tìm kiếm k-NN trong Postgres: {e}")
            return []

    def get_document_count(self) -> int:
        if not self.is_connected:
            return 0
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM historical_tasks;")
                    count = cur.fetchone()[0]
                    return count
        except Exception:
            return 0

    def add_documents(self, docs: List[Dict[str, Any]]) -> int:
        """Phương thức tương thích chuẩn để nạp danh sách chunks vào PostgreSQL"""
        if not docs:
            return 0
        texts = [d.get("text", "") for d in docs]
        vectors = self.embedder.embed_batch(texts)
        return self.add_historical_tasks(docs, vectors)

    def search(self, query: str, top_k: int = 3, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Tìm kiếm k-NN tương thích hoàn toàn với RAGEstimator:
        1. Embed câu query text thành Dense Vector 128D
        2. Chạy k-NN Cosine Similarity (<=>) trực tiếp trên PostgreSQL HNSW index
        """
        query_vec = self.embedder.embed_text(query)
        matches = self.search_similar_tasks(query_vec, top_k=top_k, min_similarity=0.0)

        # Định dạng chuẩn hóa khớp 1-1 với TinyVectorDB
        results = []
        for m in matches:
            sim = m["similarity_score"]
            results.append({
                "document": m,
                "similarity_score": sim,
                "relevance_percent": round(max(0.0, sim) * 100, 1),
                "euclidean_distance": round(float(np.sqrt(max(0.0, 2.0 * (1.0 - sim)))), 4),
                "ticket_key": m.get("ticket_key", ""),
                "title": m.get("title", ""),
                "module": m.get("module", ""),
                "task_type": m.get("task_type", ""),
                "actual_hours": m.get("actual_hours", 0.0),
                "estimated_hours": m.get("estimated_hours", 0.0),
                "story_points": m.get("story_points", 0)
            })
        return results

    def get_all_historical_tasks(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, ticket_key, title, module, task_type, tech_stack,
                               description, actual_hours, story_points, priority,
                               created_at
                        FROM historical_tasks
                        ORDER BY id ASC;
                    """)
                    return list(cur.fetchall())
        except Exception:
            return []
