"""
CLI Demo: Vector Data & RAG Ticket Logger
Chạy toàn bộ pipeline từ File Excel của Dev -> Vector DB -> RAG Naming & Estimate -> Jira/ADO
"""

import os
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from core.excel_parser import ExcelTaskParser
from core.chunker import TaskChunker
from core.vector_engine import TinyVectorDB, DenseSemanticEmbedder
from core.pgvector_store import PgVectorStore
from core.rag_estimator import RAGEstimator
from core.jira_ado_service import JiraAdoIntegrationService
from core.rules_engine import StandardRulesEngine


def main():
    console = Console()
    console.print(Panel.fit(
        "[bold cyan]AI-POWERED TASK GENERATION & VECTOR RAG DEMO[/bold cyan]\n"
        "[dim]Xử lý File Excel từ Dev -> PostgreSQL + pgvector -> Chuẩn hoá Naming & Estimate -> Jira/ADO[/dim]",
        border_style="cyan"
    ))

    base_dir = "/Users/user/Documents/AI"
    hist_file = os.path.join(base_dir, "data", "historical_dev_backlog.xlsx")
    new_req_file = os.path.join(base_dir, "data", "new_requirement_input.xlsx")

    # =========================================================================
    # STEP A & B & C & D: DATA PREPARATION (Theo Diagram của User)
    # =========================================================================
    console.print("\n[bold yellow]═══ [PHẦN 1: DATA PREPARATION (A -> B -> C -> D)] ═══[/bold yellow]")

    # A: Information Extraction
    console.print("[cyan][A] Information Extraction:[/cyan] Đọc file Excel lịch sử dev...")
    parser = ExcelTaskParser(hist_file)
    hist_raw_tasks = parser.parse_sheet()
    console.print(f" -> Trích xuất thành công [bold green]{len(hist_raw_tasks)}[/bold green] tickets từ Excel.")

    # B: Chunking
    console.print("[cyan][B] Semantic Chunking:[/cyan] Đóng gói thành chunks có ngữ cảnh kỹ thuật & metadata...")
    chunks = [TaskChunker.create_semantic_chunk(t, is_historical=True) for t in hist_raw_tasks]

    # C & D: Embedding & Vector Database
    console.print("[cyan][C & D] Embedding & Vector DB:[/cyan] Khởi tạo không gian vector 128D...")
    pg_store = PgVectorStore(dimension=128)
    if pg_store.is_connected:
        vector_db = pg_store
        db_name = "PostgreSQL 14 + pgvector (HNSW Index)"
    else:
        vector_db = TinyVectorDB(dimension=128)
        db_name = "TinyVectorDB (In-Memory Fallback)"

    vector_db.add_documents(chunks)
    console.print(f" -> Đã nạp [bold green]{vector_db.get_document_count()}[/bold green] vectors vào [bold magenta]{db_name}[/bold magenta].")

    # Hiển thị mẫu vector đầu tiên
    embedder = DenseSemanticEmbedder(dimension=128)
    sample_vec = embedder.embed_text(chunks[0]["text"])[:8]
    formatted_vec = "[" + ", ".join([f"{v:.4f}" for v in sample_vec]) + ", ... 120 dims]"
    console.print(f" -> Mẫu Vector PROJ-101 (128D Float32): [magenta]{formatted_vec}[/magenta]")

    # =========================================================================
    # STEP 1 -> 5: RETRIEVAL AUGMENTED GENERATION (Theo Diagram)
    # =========================================================================
    console.print("\n[bold yellow]═══ [PHẦN 2: RETRIEVAL AUGMENTED GENERATION (1 -> 5)] ═══[/bold yellow]")
    console.print("[cyan][Step 1 & Input][/cyan] Đọc file Excel yêu cầu mới từ Dev...")
    new_parser = ExcelTaskParser(new_req_file)
    new_tasks = new_parser.parse_sheet()
    console.print(f" -> Nhận được [bold green]{len(new_tasks)}[/bold green] raw tasks từ Dev.")

    estimator = RAGEstimator(vector_db)
    analyzed_tasks = []

    table = Table(title="[bold green]Kết quả Phân tích RAG & Naming & Estimate[/bold green]", show_header=True, header_style="bold magenta")
    table.add_column("STT", justify="center", width=4)
    table.add_column("Dev Raw Task", style="white", width=28)
    table.add_column("Standardized Naming", style="cyan", width=34)
    table.add_column("Top Similar Historical Task", style="dim", width=28)
    table.add_column("Cosine Sim", justify="center", style="yellow", width=12)
    table.add_column("AI Est (SP)", justify="center", style="green", width=12)
    table.add_column("Phase 2 Flag", justify="center", width=16)

    for idx, raw_t in enumerate(new_tasks, 1):
        result = estimator.analyze_and_estimate_task(raw_t, top_k=2)
        analyzed_tasks.append(result)

        top_match = result["similar_historical_tasks"][0] if result["similar_historical_tasks"] else None
        top_match_str = f"{top_match['ticket_key']}: {top_match['title'][:20]}..." if top_match else "None"
        sim_str = f"{top_match['similarity']}%" if top_match else "0%"

        flag_style = "bold green" if result["flag_status"] == "READY_TO_IMPORT" else "bold red"
        table.add_row(
            str(idx),
            raw_t["title"][:26] + "..." if len(raw_t["title"]) > 26 else raw_t["title"],
            result["standardized_title"],
            top_match_str,
            sim_str,
            f"{result['estimated_hours']}h ({result['story_points']} SP)",
            f"[{flag_style}]{result['flag_status']}[/{flag_style}]"
        )

    console.print(table)

    # =========================================================================
    # PHASE 2: APPROVAL & IMPORT TO JIRA / ADO
    # =========================================================================
    console.print("\n[bold yellow]═══ [PHẦN 3: PHASE 2 - APPROVAL & JIRA/ADO LOGGING] ═══[/bold yellow]")
    import_result = JiraAdoIntegrationService.execute_import(analyzed_tasks, target_platform="Jira")

    console.print(f" -> [bold green]Thành công import:[/bold green] {import_result['success_count']} tickets lên Jira.")
    console.print(f" -> [bold red]Giữ lại để Dev sửa:[/bold red] {import_result['skipped_count']} tasks.")

    if import_result["imported_tickets"]:
        sample_ticket = import_result["imported_tickets"][0]
        console.print(Panel(
            f"[bold]Ticket Key:[/bold] {sample_ticket['ticket_key']}\n"
            f"[bold]Summary:[/bold] {sample_ticket['title']}\n"
            f"[bold]Estimate:[/bold] {sample_ticket['estimated_hours']} hours ({sample_ticket['story_points']} Story Points)\n"
            f"[bold]Simulated Endpoint:[/bold] {sample_ticket['api_endpoint']}",
            title="[green]Mẫu Ticket Jira được khởi tạo tự động[/green]"
        ))

    # =========================================================================
    # STEP 4: GSD / SUPER POWER RULES GENERATION
    # =========================================================================
    console.print("\n[bold yellow]═══ [PHẦN 4: GSD / SUPER POWER RULES GENERATOR] ═══[/bold yellow]")
    rules_path = StandardRulesEngine.save_rules_file()
    console.print(f" -> Đã sinh file quy chuẩn độc lập: [bold cyan]{rules_path}[/bold cyan]")
    console.print(" -> Đảm bảo rules được scope nghiêm ngặt, [bold green]KHÔNG ảnh hưởng sang các chat session khác![/bold green]")


if __name__ == "__main__":
    main()
