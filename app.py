"""
Flask Web Application: AI-Powered Task Breakdown, Vector RAG & Jira/ADO Logger
Môi trường demo tương tác đồ họa cho quy trình Vector Data và Log Ticket.
"""

import os
import io
import json
import time
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd

from core.excel_parser import ExcelTaskParser
from core.chunker import TaskChunker
from core.vector_engine import TinyVectorDB, DenseSemanticEmbedder
from core.pgvector_store import PgVectorStore
from core.rag_estimator import RAGEstimator
from core.jira_ado_service import JiraAdoIntegrationService
from core.rules_engine import StandardRulesEngine

app = Flask(__name__)
app.config["SECRET_KEY"] = "ai-vector-jira-secret-key-2026"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

BASE_DIR = "/Users/user/Documents/AI"
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global State trong bộ nhớ
GLOBAL_STATE = {
    "vector_db": None,
    "active_db_type": "Initializing...",
    "historical_tasks": [],
    "historical_chunks": [],
    "dev_raw_tasks": [],
    "analyzed_tasks": [],
    "import_history": [],
    "active_hist_file": os.path.join(DATA_DIR, "historical_dev_backlog.xlsx"),
    "active_dev_file": os.path.join(DATA_DIR, "new_requirement_input.xlsx")
}


def initialize_default_db():
    """Khởi tạo nạp dữ liệu lịch sử vào PostgreSQL + pgvector (hoặc TinyVectorDB fallback)"""
    try:
        # 1. Thử kết nối PostgreSQL + pgvector trước
        pg_store = PgVectorStore(dimension=128)
        if pg_store.is_connected:
            GLOBAL_STATE["vector_db"] = pg_store
            GLOBAL_STATE["active_db_type"] = "PostgreSQL 14 + pgvector (HNSW Index)"
            print("[Init] Sử dụng Enterprise Storage: PostgreSQL + pgvector.")
        else:
            GLOBAL_STATE["vector_db"] = TinyVectorDB(dimension=128)
            GLOBAL_STATE["active_db_type"] = "TinyVectorDB (In-Memory Fallback)"
            print("[Init Warning] PostgreSQL offline. Fallback sang TinyVectorDB in-memory.")

        # 2. Đọc file Excel lịch sử và nạp vào database
        if os.path.exists(GLOBAL_STATE["active_hist_file"]):
            parser = ExcelTaskParser(GLOBAL_STATE["active_hist_file"])
            tasks = parser.parse_sheet()
            GLOBAL_STATE["historical_tasks"] = tasks

            chunks = [TaskChunker.create_semantic_chunk(t, is_historical=True) for t in tasks]
            GLOBAL_STATE["historical_chunks"] = chunks

            inserted = GLOBAL_STATE["vector_db"].add_documents(chunks)
            print(f"[Init] Đã nạp {inserted} historical vectors vào {GLOBAL_STATE['active_db_type']}.")
    except Exception as e:
        print(f"[Init Warning] Chưa thể nạp DB mặc định: {e}")


initialize_default_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/slides")
def slides():
    return render_template("slides.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    vdb = GLOBAL_STATE["vector_db"]
    return jsonify({
        "status": "online",
        "llm_model": "Gemini-3-Flash",
        "db_engine": GLOBAL_STATE.get("active_db_type", "PostgreSQL 14 + pgvector"),
        "vector_db_count": vdb.get_document_count() if vdb else 0,
        "vector_dimension": vdb.dimension if vdb else 128,
        "historical_count": len(GLOBAL_STATE["historical_tasks"]),
        "dev_tasks_count": len(GLOBAL_STATE["dev_raw_tasks"]),
        "analyzed_tasks_count": len(GLOBAL_STATE["analyzed_tasks"]),
        "hist_file": os.path.basename(GLOBAL_STATE["active_hist_file"]),
        "dev_file": os.path.basename(GLOBAL_STATE["active_dev_file"])
    })


@app.route("/api/data-prep/inspect", methods=["GET"])
def inspect_data_prep():
    """Trả về chi tiết các bước A -> B -> C -> D để hiển thị lên UI trực quan"""
    vdb = GLOBAL_STATE["vector_db"]
    embedder = DenseSemanticEmbedder(dimension=128)

    # Sample vector for visualization (lấy từ chunk lịch sử đầu tiên)
    sample_vector_data = []
    if GLOBAL_STATE["historical_chunks"]:
        first_chunk = GLOBAL_STATE["historical_chunks"][0]
        sample_vec = embedder.embed_text(first_chunk.get("text", ""))
        sample_vector_data = {
            "ticket_key": first_chunk.get("ticket_key", "PROJ-101"),
            "title": first_chunk.get("title", "Task"),
            "dimension": 128,
            "vector_snippet": sample_vec[:24].tolist(),  # lấy 24 chiều đầu để render heatmap
            "vector_full_length": 128
        }

    return jsonify({
        "step_a_extraction": {
            "title": "Information Extraction (Step A)",
            "file": os.path.basename(GLOBAL_STATE["active_hist_file"]),
            "total_extracted": len(GLOBAL_STATE["historical_tasks"]),
            "items": GLOBAL_STATE["historical_tasks"][:5]
        },
        "step_b_chunking": {
            "title": "Semantic Chunking (Step B)",
            "total_chunks": len(GLOBAL_STATE["historical_chunks"]),
            "sample_chunk": GLOBAL_STATE["historical_chunks"][0] if GLOBAL_STATE["historical_chunks"] else None
        },
        "step_c_embedding": {
            "title": "Dense Subword Embedding (Step C)",
            "dimension": 128,
            "sample": sample_vector_data
        },
        "step_d_vectordb": {
            "title": GLOBAL_STATE.get("active_db_type", "PostgreSQL 14 + pgvector"),
            "indexed_count": vdb.get_document_count() if vdb else 0,
            "metric": "Cosine Similarity / HNSW Vector Index (<=>)"
        }
    })


@app.route("/api/search-vectors", methods=["POST"])
def search_vectors():
    """Step 1 & 2 & 3: Query -> Embedding -> Vector DB Search -> Relevant Historical Data"""
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    top_k = int(data.get("top_k", 3))

    if not query:
        return jsonify({"error": "Vui lòng nhập câu truy vấn"}), 400

    vdb = GLOBAL_STATE["vector_db"]
    results = vdb.search(query=query, top_k=top_k)

    # Lấy vector của chính query để minh hoạ phép chiếu không gian
    query_vec = vdb.embedder.embed_text(query)[:16].tolist()

    return jsonify({
        "query": query,
        "query_vector_sample": query_vec,
        "top_k": top_k,
        "matches": results
    })


@app.route("/api/load-dev-excel", methods=["POST"])
def load_dev_excel():
    """Nạp file Excel mới của Dev để phân tích"""
    file = request.files.get("file")
    if file and file.filename.endswith((".xlsx", ".xls")):
        save_path = os.path.join(DATA_DIR, file.filename)
        file.save(save_path)
        GLOBAL_STATE["active_dev_file"] = save_path
    else:
        # Dùng file mặc định nếu không upload
        GLOBAL_STATE["active_dev_file"] = os.path.join(DATA_DIR, "new_requirement_input.xlsx")

    parser = ExcelTaskParser(GLOBAL_STATE["active_dev_file"])
    tasks = parser.parse_sheet()
    GLOBAL_STATE["dev_raw_tasks"] = tasks

    return jsonify({
        "message": f"Nạp thành công {len(tasks)} tasks từ file Excel",
        "file_name": os.path.basename(GLOBAL_STATE["active_dev_file"]),
        "tasks": tasks
    })


@app.route("/api/analyze-requirements", methods=["POST"])
def analyze_requirements():
    """
    RAG Pipeline:
    Đọc toàn bộ raw tasks trong Excel của Dev -> Tra cứu Vector DB -> Chuẩn hoá Naming ->
    Tính toán Estimate (Hours, SP) -> Flag Phase 2
    """
    if not GLOBAL_STATE["dev_raw_tasks"]:
        if os.path.exists(GLOBAL_STATE["active_dev_file"]):
            parser = ExcelTaskParser(GLOBAL_STATE["active_dev_file"])
            GLOBAL_STATE["dev_raw_tasks"] = parser.parse_sheet()

    tasks_to_process = GLOBAL_STATE["dev_raw_tasks"]
    if not tasks_to_process:
        return jsonify({"error": "Chưa có dữ liệu task từ Dev Excel"}), 400

    estimator = RAGEstimator(GLOBAL_STATE["vector_db"])
    analyzed = []
    for raw_t in tasks_to_process:
        res = estimator.analyze_and_estimate_task(raw_t, top_k=3)
        analyzed.append(res)

    GLOBAL_STATE["analyzed_tasks"] = analyzed

    ready_count = sum(1 for t in analyzed if t["flag_status"] == "READY_TO_IMPORT")
    warning_count = sum(1 for t in analyzed if t["flag_status"] != "READY_TO_IMPORT")

    return jsonify({
        "message": "Phân tích RAG thành công",
        "total_analyzed": len(analyzed),
        "ready_count": ready_count,
        "warning_count": warning_count,
        "tasks": analyzed
    })


@app.route("/api/update-task-approval", methods=["POST"])
def update_task_approval():
    """Phase 2: Người dùng bật/tắt duyệt (Approve) hoặc sửa title/estimate cho từng task"""
    data = request.get_json() or {}
    task_idx = data.get("index")
    is_approved = data.get("is_approved")
    custom_title = data.get("standardized_title")
    custom_hours = data.get("estimated_hours")

    if task_idx is not None and 0 <= task_idx < len(GLOBAL_STATE["analyzed_tasks"]):
        target = GLOBAL_STATE["analyzed_tasks"][task_idx]
        if is_approved is not None:
            target["is_approved"] = bool(is_approved)
        if custom_title:
            target["standardized_title"] = custom_title
        if custom_hours is not None:
            target["estimated_hours"] = float(custom_hours)
            target["story_points"] = RAGEstimator._hours_to_story_points(float(custom_hours))
        return jsonify({"success": True, "task": target})

    return jsonify({"error": "Task index không hợp lệ"}), 400


@app.route("/api/import-tickets", methods=["POST"])
def import_tickets():
    """
    Phase 2 Import:
    Bắn các tasks ĐÃ APPROVE và READY lên Jira hoặc Azure DevOps (ADO).
    Các task chưa approve hoặc fail/warning sẽ được giữ lại trên màn hình.
    """
    data = request.get_json() or {}
    platform = data.get("platform", "Jira")  # "Jira" hoặc "ADO"
    project_key = data.get("project_key", "PROJ")

    tasks = GLOBAL_STATE["analyzed_tasks"]
    if not tasks:
        return jsonify({"error": "Chưa có danh sách task đã phân tích"}), 400

    result = JiraAdoIntegrationService.execute_import(tasks, target_platform=platform, project_key=project_key)
    GLOBAL_STATE["import_history"].append(result)

    return jsonify(result)


@app.route("/api/rules", methods=["GET"])
def get_rules():
    """Lấy quy chuẩn GSD / Super Power và nội dung file .agent-rules.md"""
    rules_md = StandardRulesEngine.generate_project_rules_markdown()
    schema = StandardRulesEngine.DEFAULT_STANDARD_INPUT_SCHEMA
    return jsonify({
        "markdown": rules_md,
        "schema": schema
    })


@app.route("/api/export-excel", methods=["GET"])
def export_excel():
    """Xuất danh sách task đã chuẩn hoá và estimate thành file Excel để tải về"""
    tasks = GLOBAL_STATE["analyzed_tasks"]
    if not tasks:
        return jsonify({"error": "Chưa có task để xuất"}), 400

    rows = []
    for t in tasks:
        rows.append({
            "Original_Task": t.get("original_title"),
            "Standardized_Jira_Title": t.get("standardized_title"),
            "Module": t.get("module"),
            "Type": t.get("task_type"),
            "AI_Estimated_Hours": t.get("estimated_hours"),
            "Story_Points": t.get("story_points"),
            "Priority": t.get("priority"),
            "Flag_Status": t.get("flag_status"),
            "Is_Approved": "YES" if t.get("is_approved") else "NO",
            "Acceptance_Criteria": " | ".join(t.get("acceptance_criteria", []))
        })

    df = pd.DataFrame(rows)
    output_stream = io.BytesIO()
    with pd.ExcelWriter(output_stream, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="AI_Normalized_Tasks")
    output_stream.seek(0)

    return send_file(
        output_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="jira_tasks_estimated.xlsx"
    )


if __name__ == "__main__":
    print(f"Khởi động AI Vector Task Web App tại: http://127.0.0.1:5005")
    app.run(host="0.0.0.0", port=5005, debug=False)
