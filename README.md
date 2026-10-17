# AI-Powered Jira/ADO Task Breakdown & Vector RAG Engine

Hệ thống AI chuyên biệt tiếp nhận file **Excel từ Dev**, phân tích ngữ cảnh, áp dụng **Vector Data / RAG Pipeline** dựa trên dữ liệu lịch sử dự án, tự động chuẩn hoá **Naming convention `[TYPE][MODULE]`**, tính toán **Ước lượng thời gian (Estimated Hours & Story Points)** theo trọng số tương đồng hình học, và tích hợp đồng bộ tự động lên **Jira Cloud** hoặc **Azure DevOps (ADO)**.

---

## 1. Kiến Trúc Hoạt Động (Mapping theo sơ đồ RAG chuẩn)

Hệ thống được thiết kế khớp 1-1 với 2 chu trình chính trong sơ đồ kiến trúc:

### Chu trình 1: Data Preparation (Indexing Pipeline)
- **Raw Data Sources:** File Excel lịch sử hoàn thành (`data/historical_dev_backlog.xlsx`) chứa ticket key, actual hours, tech stack, mô tả chi tiết.
- **[A] Information Extraction:** Parser thông minh (`core/excel_parser.py`) trích xuất các cột dữ liệu không đồng nhất từ nhiều Dev/BA khác nhau thành JSON có cấu trúc.
- **[B] Chunking:** Phân mảnh ngữ nghĩa (`core/chunker.py`) gom nhóm thành các đơn vị Task hoàn chỉnh kèm metadata kỹ thuật.
- **[C] Embedding:** Vector hóa ngữ nghĩa (`core/vector_engine.py`) biến văn bản kỹ thuật thành Dense Vector 128 chiều số thực float32 với chuẩn hoá độ dài L2 Norm = 1.0.
- **[D] Vector Database:** Lưu trữ Vector + Metadata trong **PostgreSQL 14 + `pgvector`** với chỉ mục **HNSW Cosine Index** (`core/pgvector_store.py`), hỗ trợ fallback in-memory `TinyVectorDB`.

### Chu trình 2: Retrieval Augmented Generation (Inference Pipeline)
- **[1] Query (Dev Story/Excel):** File Excel yêu cầu mới từ Dev (`data/new_requirement_input.xlsx`) cần phân tích và log ticket.
- **[2] Vector Search (k-NN):** Vector hoá yêu cầu mới và so sánh Cosine Similarity ($Sim(u,v) = u \cdot v$) với toàn bộ kho ticket quá khứ.
- **[3] Relevant Data:** Trích xuất Top-K ticket quá khứ có ngữ cảnh tương đồng cao nhất kèm giờ làm thực tế (`actual_hours`).
- **[4] LLM / Context Synthesis:** Ghép Query + Relevant Historical Tasks + Project Rules để tổng hợp logic với **Gemini-3-Flash**.
- **[5] Jira/ADO Response & Log Ticket:**
  - Chuẩn hoá Naming: `[BE][AUTH]...`, `[FE][AUTH]...`, `[DB][PAYMENT]...`
  - Ước lượng giờ theo công thức trọng số tương đồng:
    $$\text{Estimated\_Hours} = \frac{\sum_{i=1}^K \text{Sim}_i \times \text{Actual\_Hours}_i}{\sum_{i=1}^K \text{Sim}_i}$$
  - Quy đổi Story Points theo Fibonacci ($1, 2, 3, 5, 8, 13, 21$).
  - Đánh cờ Phase 2: `READY_TO_IMPORT`, `WARNING_DUPLICATE` (nếu Sim $\ge 85\%$), `NEEDS_INPUT`.
  - Bắn API lên Atlassian Jira REST API v3 hoặc Azure DevOps JSON Patch.

---

## 2. Cấu Trúc Thư Mục Dự Án

```
/Users/user/Documents/AI/
├── core/
│   ├── excel_parser.py        # [A] Đọc & chuẩn hoá mọi format Excel của Dev
│   ├── chunker.py             # [B] Semantic chunking đóng gói metadata
│   ├── vector_engine.py       # [C & 1-3] Dense Embedder 128D & Cosine Math
│   ├── pgvector_store.py      # [D] Enterprise PostgreSQL + pgvector (HNSW Index)
│   ├── llm_service.py         # [4] Gemini-3-Flash LLM – Context Synthesis & Gherkin AC
│   ├── rag_estimator.py       # [4 & 5] RAG Naming, Similarity Estimate & AC
│   ├── jira_ado_service.py    # Phase 2: Selective Approval & Jira/ADO API sync
│   └── rules_engine.py        # Step 1 & 4: GSD / Super Power Rules Generator
├── data/
│   ├── historical_dev_backlog.xlsx  # Dữ liệu nguồn lịch sử mẫu
│   └── new_requirement_input.xlsx   # File Excel Dev nhập cần phân tích
├── static/
│   ├── css/style.css          # Design System Cyberpunk Dark Theme Glassmorphism
│   └── js/app.js              # Tương tác Dashboard, trực quan hoá Heatmap 128D
├── templates/
│   ├── index.html             # Web App Dashboard trực quan
│   └── slides.html            # Slide thuyết trình tự động generate
├── app.py                     # Flask Web Application (cổng 5005)
├── cli_demo.py                # Command-Line Demo với rich terminal output
├── .agent-rules.md            # File Rules biệt lập (GSD Spec, không ô nhiễm chat khác)
└── README.md
```

---

## 3. Phân Tích Chi Tiết Từng Module

### 3.1 `core/excel_parser.py` — Data Ingestion Layer
- **Chức năng:** Đọc file Excel (.xlsx) nhiều định dạng khác nhau (Dev tự do điền), chuẩn hoá cột `title`, `module`, `task_type`, `tech_stack`, `description`, `actual_hours`, `story_points`.
- **Kỹ thuật:** Fuzzy column matching, fallback giá trị mặc định, xử lý merged cells, strip whitespace/newline.
- **Output:** List[Dict] cấu trúc chuẩn truyền sang `chunker.py`.

### 3.2 `core/chunker.py` — Semantic Chunking
- **Chức năng:** Gộp metadata task thành text chunk liên tục để embedding không bị mất context.
- **Kỹ thuật:** Concatenate fields theo thứ tự ưu tiên ngữ nghĩa (`title > description > tech_stack > module`), loại bỏ redundant token.
- **Output:** Text string đại diện ngữ nghĩa đầy đủ của mỗi ticket.

### 3.3 `core/vector_engine.py` — Embedding Engine (128D Dense Vector)
- **Chức năng:** Vector hoá text kỹ thuật thành Dense Vector 128 chiều, tính Cosine Similarity giữa query vector và corpus.
- **Kỹ thuật:**
  - `DenseSemanticEmbedder`: Hash-based + TF-IDF-like weighting cho 128D output (không phụ thuộc model ngoài).
  - L2 Normalization: `v = v / ||v||` → dot product = cosine similarity.
  - Cosine Similarity: $\text{Sim}(u,v) = u \cdot v$ (do đã normalize).
- **Output:** `np.ndarray` shape `(128,)`, dtype `float32`.

### 3.4 `core/pgvector_store.py` — Enterprise Vector Database
- **Chức năng:** Lưu trữ persistent vector + metadata lên PostgreSQL 14 với extension `pgvector`, tìm kiếm k-NN bằng HNSW index.
- **Kỹ thuật:**
  - Table: `task_vectors(id, ticket_key, title, module, task_type, tech_stack, actual_hours, story_points, embedding vector(128))`
  - Index: `CREATE INDEX USING hnsw (embedding vector_cosine_ops)` — tốc độ ANN search O(log N).
  - Query: `ORDER BY embedding <=> $1 LIMIT k` (toán tử `<=>` = cosine distance).
  - Fallback: Nếu PostgreSQL offline → dùng `TinyVectorDB` in-memory.
- **Output:** List[Dict] Top-K similar tasks kèm `relevance_percent`.

### 3.5 `core/llm_service.py` — Gemini-3-Flash LLM Integration
- **Chức năng:** Gọi mô hình **Gemini-3-Flash** qua OpenAI SDK (custom endpoint) để sinh ra:
  - `standardized_title`: Chuẩn hoá theo `[TYPE][MODULE] <Action>`.
  - `acceptance_criteria`: Đúng 3 tiêu chí Gherkin (`Given/When/Then`).
  - `estimated_hours`: Dựa trên baseline RAG và reasoning.
  - `story_points`: Fibonacci scale.
  - `technical_reasoning`: Giải thích 2-3 câu.
- **Kỹ thuật:**
  - Endpoint: `https://aiportalapi.stu-platform.live/jpe`
  - SDK method: `client.responses.create(model="Gemini-3-Flash", input=prompt)`
  - Response: `resp.output_text` → strip markdown → `json.loads()`.
  - Fallback: Nếu LLM lỗi → trả về `None` → RAG estimator dùng kết quả toán học thuần.
- **Output:** Dict JSON structured hoặc `None`.

### 3.6 `core/rag_estimator.py` — RAG Inference Orchestrator
- **Chức năng:** Điều phối toàn bộ luồng RAG inference: embed query → search vector DB → tính baseline → gọi LLM → merge kết quả.
- **Kỹ thuật:**
  - Weighted similarity estimate: $\hat{h} = \frac{\sum \text{Sim}_i \times h_i}{\sum \text{Sim}_i}$
  - Story points mapping: `{≤2h: 1pt, ≤4h: 2pt, ≤8h: 3pt, ≤16h: 5pt, ≤24h: 8pt, >24h: 13pt}`
  - Status flag: `READY_TO_IMPORT / WARNING_DUPLICATE / NEEDS_INPUT`
  - LLM synthesis: Gọi `GeminiFlashLLM.synthesize_task()` với Top-K context.
- **Output:** Full analysis dict với title, hours, SP, AC, flag, reasoning.

### 3.7 `core/jira_ado_service.py` — Integration Layer
- **Chức năng:** Bắn kết quả phân tích lên Jira Cloud hoặc Azure DevOps qua REST API.
- **Kỹ thuật:**
  - Jira: `POST /rest/api/3/issue` với payload ADF (Atlassian Document Format).
  - ADO: `POST /_apis/wit/workitems/$Task` với JSON Patch operations.
  - Payload bao gồm: Gherkin AC, LLM model name, estimated hours, story points, technical reasoning.
  - Auth: `Basic Auth` (Jira) hoặc `Bearer Token` (ADO).

### 3.8 `core/rules_engine.py` — Business Rules Layer
- **Chức năng:** Nạp và áp dụng GSD Spec Rules từ `.agent-rules.md` để validate naming, enforce guardrails.
- **Kỹ thuật:** Markdown rule parsing, regex pattern matching cho `[TYPE][MODULE]` format.

---

## 4. Các Tool & Công Nghệ Được Áp Dụng

| # | Tool / Công Nghệ | Vai Trò | Layer |
|---|-----------------|---------|-------|
| 1 | **Python 3.11+** | Runtime chính | Core |
| 2 | **Flask** | REST API & Web Dashboard (port 5005) | API |
| 3 | **OpenAI Python SDK** | Gọi Gemini-3-Flash qua custom endpoint | LLM |
| 4 | **Gemini-3-Flash** | LLM sinh AC Gherkin, chuẩn hoá naming, reasoning | AI/LLM |
| 5 | **PostgreSQL 14** | Enterprise vector storage persistent | DB |
| 6 | **pgvector** | Extension vector(128) + `<=>` cosine distance operator | DB |
| 7 | **HNSW Index** | Approximate Nearest Neighbor (ANN) search O(log N) | DB |
| 8 | **psycopg2** | Python driver kết nối PostgreSQL | DB |
| 9 | **NumPy** | Dense vector operations, L2 normalization | Math |
| 10 | **openpyxl / pandas** | Đọc & parse file Excel đa định dạng | Data |
| 11 | **Atlassian Jira REST API v3** | Tạo issue lên Jira Cloud | Integration |
| 12 | **Azure DevOps REST API** | Tạo Work Item lên ADO | Integration |
| 13 | **TinyVectorDB** | In-memory vector fallback khi Postgres offline | Fallback |
| 14 | **HTML/CSS/JS** | Web Dashboard (Cyberpunk Dark + Glassmorphism) | Frontend |
| 15 | **Regex + JSON** | Sanitize LLM output, strip markdown blocks | Util |

---

## 5. Luồng End-to-End (Step-by-Step)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     END-TO-END FLOW                                  │
└─────────────────────────────────────────────────────────────────────┘

PHASE A — INDEXING (Chạy 1 lần khi khởi động)
──────────────────────────────────────────────
Step 1  [excel_parser.py]
        Đọc data/historical_dev_backlog.xlsx
        → Chuẩn hoá 10 ticket lịch sử thành List[Dict]

Step 2  [chunker.py]
        Mỗi ticket → text chunk ngữ nghĩa liên tục

Step 3  [vector_engine.py — DenseSemanticEmbedder]
        Text chunk → Dense Vector 128D (float32, L2-normalized)

Step 4  [pgvector_store.py]
        INSERT vào PostgreSQL: embedding vector(128) + metadata
        → HNSW Index tự động build

PHASE B — INFERENCE (Mỗi khi Dev submit task mới)
──────────────────────────────────────────────────
Step 5  [app.py / cli_demo.py]
        Dev input: title + module + type + tech_stack + description
        (Qua Web Form hoặc CLI)

Step 6  [rag_estimator.py → vector_engine.py]
        Input → Dense Vector 128D

Step 7  [pgvector_store.py]
        Vector query <=> HNSW Index
        → Top-K (mặc định K=5) ticket tương đồng nhất
        → Trả về: ticket_key, title, actual_hours, relevance_percent

Step 8  [rag_estimator.py]
        Tính baseline:
        Estimated_Hours = Σ(Sim_i × Hours_i) / Σ(Sim_i)
        Story Points = Fibonacci mapping

Step 9  [llm_service.py — GeminiFlashLLM]
        Prompt = Query + Top-K context + GSD Rules
        → Gemini-3-Flash synthesize:
           • standardized_title [TYPE][MODULE]
           • 3x Gherkin Acceptance Criteria
           • estimated_hours (LLM-adjusted)
           • story_points
           • technical_reasoning

Step 10 [rag_estimator.py]
        Merge LLM output + RAG baseline
        → Đánh flag: READY_TO_IMPORT / WARNING_DUPLICATE / NEEDS_INPUT

Step 11 [jira_ado_service.py] (Phase 2 — Khi approved)
        POST to Jira Cloud REST API v3
        hoặc POST to Azure DevOps JSON Patch API
        → Ticket được tạo với đầy đủ AC + SP + Hours + Reasoning
```

---

## 6. Hướng Dẫn Demo (Step-by-Step)

### Bước 0 — Chuẩn Bị (Chỉ làm 1 lần)

```bash
# 1. Cài dependencies
pip install flask openai psycopg2-binary numpy openpyxl pandas

# 2. Tạo PostgreSQL database
createdb ai_vector_rag

# 3. Bật pgvector extension (trong psql)
psql ai_vector_rag -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Bước 1 — Khởi Động Server

```bash
python3 app.py
```

Expected output:
```
[PgVectorStore] Đã kết nối thành công PostgreSQL ...
[Init] Đã nạp 10 historical vectors vào PostgreSQL 14 + pgvector (HNSW Index).
Khởi động AI Vector Task Web App tại: http://127.0.0.1:5005
```

### Bước 2 — Demo Web Dashboard

1. Mở trình duyệt tại **`http://127.0.0.1:5005`**
2. Kiểm tra status bar: **PostgreSQL + pgvector** ✅ | **Gemini-3-Flash** ✅ | **10 vectors** ✅
3. Nhập task mới vào form:
   - **Title:** `Implement 2FA authentication with TOTP`
   - **Module:** `AUTH`
   - **Type:** `Backend`
   - **Tech Stack:** `Node.js, Redis, TOTP`
   - **Description:** `Implement Time-based One-Time Password with QR code enrollment`
4. Nhấn **"Phân Tích RAG"** → Xem kết quả:
   - 🎯 Standardized title: `[BE][AUTH] Implement TOTP 2FA with QR enrollment`
   - ⏱ Estimated Hours: `8h` (từ LLM + RAG baseline)
   - 📊 Story Points: `5` (Fibonacci)
   - ✅ 3 Gherkin ACs
   - 🧠 Technical Reasoning từ Gemini-3-Flash
   - 🔍 Top-5 similar tickets từ pgvector HNSW search

### Bước 3 — Demo Vector Search Trực Quan

1. Vào tab **"Vector Data"** trên Dashboard
2. Xem **Heatmap 128D** của embedding vector
3. Xem danh sách Top-K similar tickets với cosine similarity %
4. Inspect PostgreSQL query: `ORDER BY embedding <=> $1 LIMIT 5`

### Bước 4 — Demo Jira/ADO Integration (Phase 2)

1. Sau khi phân tích xong, nhấn **"Push to Jira"** hoặc **"Push to ADO"**
2. Điền Jira URL + API Token (hoặc ADO PAT)
3. System tạo issue với full payload: title, AC, hours, SP, reasoning
4. Confirm trên Jira/ADO dashboard

### Bước 5 — Demo Slide Thuyết Trình

Mở **`http://127.0.0.1:5005/slides`** để xem toàn bộ kiến trúc hệ thống dạng slide.

### Bước 6 — Demo CLI (Terminal Mode)

```bash
python3 cli_demo.py
```

Terminal sẽ hiển thị toàn bộ RAG pipeline với rich formatting: embedding visualization, similarity scores, LLM output.

---

## 7. Hướng Dẫn Sử Dụng & Demo (Quick Start)

### Cách 1: Chạy Web Dashboard Trực Quan
```bash
python3 app.py
```
Mở trình duyệt tại: **`http://127.0.0.1:5005`**

### Cách 2: Chạy Terminal CLI Demo
```bash
python3 cli_demo.py
```

---

## 8. Cấu Hình Môi Trường (Environment Variables)

| Variable | Default | Mô tả |
|----------|---------|-------|
| `LLM_MODEL` | `Gemini-3-Flash` | Tên model |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `ai_vector_rag` | Database name |

---

*Generated by AI-Powered RAG System — Gemini-3-Flash + PostgreSQL 14 + pgvector HNSW*
