"""
Module: core/rag_estimator.py
Step 4 & 5 in Diagram:
- Step 4: Relevant Data + Query -> LLM / RAG Logic
- Step 5: Response: Chuẩn hoá Naming, Dự toán Estimate (Hours & SP), sinh Acceptance Criteria, Flag trùng lặp

Thực hiện toàn bộ nghiệp vụ AI Task Generation dựa trên dữ liệu Vector lịch sử.
"""

import math
import re
from typing import List, Dict, Any, Optional
from core.vector_engine import TinyVectorDB
from core.llm_service import GeminiFlashLLM


class RAGEstimator:
    """
    Bộ suy luận RAG tích hợp:
    1. Lấy Top-K ticket tương đồng nhất từ Vector Database (Relevant Data).
    2. Gọi Gemini-3-Flash để suy luận sâu, chuẩn hóa Naming, sinh Acceptance Criteria (Gherkin).
    3. Tính toán số Estimate (Hours, Story Points) dựa trên trọng số tương đồng và lập luận kỹ thuật.
    4. Kiểm tra trùng lặp (Duplicate Detection).
    """

    FIBONACCI_SP = [1, 2, 3, 5, 8, 13, 21]

    MODULE_MAP = {
        "quản lý 2fa": "AUTH",
        "two-factor authentication": "AUTH",
        "authentication": "AUTH",
        "auth": "AUTH",
        "cổng thanh toán momo qr": "PAYMENT",
        "payment": "PAYMENT",
        "thanh toán": "PAYMENT",
        "tìm kiếm nâng cao": "SEARCH",
        "search": "SEARCH",
        "notification": "NOTI",
        "thông báo": "NOTI",
        "automation test": "QA",
        "testing": "QA",
        "devops": "DEVOPS",
        "ci/cd": "DEVOPS"
    }

    def __init__(self, vector_db: Any, llm_service: Optional[GeminiFlashLLM] = None):
        self.vector_db = vector_db
        self.llm_service = llm_service or GeminiFlashLLM()

    @staticmethod
    def _hours_to_story_points(hours: float) -> int:
        """Quy đổi giờ làm việc sang Fibonacci Story Points chuẩn Agile"""
        if hours <= 4:
            return 1
        elif hours <= 7:
            return 2
        elif hours <= 11:
            return 3
        elif hours <= 16:
            return 5
        elif hours <= 24:
            return 8
        elif hours <= 40:
            return 13
        else:
            return 21

    def _normalize_title(self, raw_title: str, module: str, task_type: str) -> str:
        """
        Chuẩn hoá Naming theo quy ước dự án:
        [TYPE][MODULE] Action
        """
        clean_title = raw_title.strip()
        # Loại bỏ các prefix cũ nếu dev gõ lung tung
        clean_title = re.sub(r"^\[.*?\]\s*", "", clean_title)

        type_tag = task_type.upper()
        if "BACKEND" in type_tag:
            type_tag = "BE"
        elif "FRONTEND" in type_tag:
            type_tag = "FE"
        elif "DATABASE" in type_tag or "DB" in type_tag:
            type_tag = "DB"
        elif "QA" in type_tag or "TEST" in type_tag:
            type_tag = "QA"
        elif "DEVOPS" in type_tag or "CI" in type_tag:
            type_tag = "DEVOPS"
        else:
            type_tag = "DEV"

        mod_lower = module.strip().lower()
        matched_mod = None
        for k, v in self.MODULE_MAP.items():
            if k in mod_lower or mod_lower in k:
                matched_mod = v
                break

        if not matched_mod:
            # Fallback lấy ký tự chữ số không dấu
            matched_mod = re.sub(r"[^A-Za-z0-9]", "", module).upper()
            if len(matched_mod) > 8:
                matched_mod = matched_mod[:8]
            if not matched_mod:
                matched_mod = "CORE"

        prefix = f"[{type_tag}][{matched_mod}]"
        return f"{prefix} {clean_title}"

    def analyze_and_estimate_task(
        self,
        task_input: Dict[str, Any],
        top_k: int = 3,
        duplicate_threshold: float = 0.85
    ) -> Dict[str, Any]:
        """
        Thực thi toàn bộ flow RAG cho 1 task từ Excel của Dev:
        1. Query -> Vector DB
        2. Lấy Relevant Historical Tasks
        3. Tính trọng số estimate
        4. Chuẩn hoá format Jira
        """
        raw_title = task_input.get("title", "")
        module = task_input.get("module", "General")
        task_type = task_input.get("task_type", "Backend")
        description = task_input.get("description", "")
        tech_stack = task_input.get("tech_stack", "")

        # 1. Tạo Query String giàu ngữ nghĩa
        query_text = f"Module: {module} | Type: {task_type} | Task: {raw_title} | Details: {description}"
        if tech_stack:
            query_text += f" | Tech: {tech_stack}"

        # 2. Vector DB Search (Relevant Data)
        similar_tasks = self.vector_db.search(query=query_text, top_k=top_k)

        # 3. Tính toán Estimate theo Similarity-Weighted Average
        total_weight = 0.0
        weighted_hours = 0.0
        top_match_info = []

        is_duplicate = False
        duplicate_with = None

        for match in similar_tasks:
            sim = match["similarity_score"]
            if sim > 0.05:
                weight = sim ** 2
                hist_hours = float(match.get("actual_hours", match.get("estimated_hours", 8.0)))
                weighted_hours += hist_hours * weight
                total_weight += weight

                top_match_info.append({
                    "ticket_key": match.get("ticket_key"),
                    "title": match.get("title"),
                    "similarity": round(sim * 100, 1),
                    "actual_hours": hist_hours,
                    "story_points": match.get("story_points")
                })

                if sim >= duplicate_threshold and not is_duplicate:
                    is_duplicate = True
                    duplicate_with = match.get("ticket_key")

        if total_weight > 0:
            suggested_hours = round(weighted_hours / total_weight, 1)
        else:
            fallback_map = {"Backend": 8.0, "Frontend": 6.0, "Database": 4.0, "QA": 6.0, "DevOps": 8.0}
            suggested_hours = fallback_map.get(task_type, 6.0)

        suggested_hours = max(1.0, min(40.0, suggested_hours))
        story_points = self._hours_to_story_points(suggested_hours)

        # 3.1. Baseline Heuristic
        standardized_title = self._normalize_title(raw_title, module, task_type)
        acceptance_criteria = [
            f"Hoàn thành logic {raw_title} không có lỗi unhandled exception.",
            f"Viết unit test tối thiểu 80% coverage cho các hàm nghiệp vụ chính.",
            f"Đảm bảo tuân thủ kiến trúc mã nguồn và naming convention của {module} module."
        ]
        if "API" in raw_title.upper() or "BE" in standardized_title:
            acceptance_criteria.append("Có tài liệu Swagger/OpenAPI cập nhật và response time < 200ms.")
        if "FE" in standardized_title or "MÀN HÌNH" in raw_title.upper():
            acceptance_criteria.append("Giao diện chuẩn UI/UX, hỗ trợ responsive mobile và desktop.")

        technical_reasoning = f"Baseline: ước lượng {suggested_hours}h dựa trên trọng số vector với {len(top_match_info)} ticket lịch sử."
        llm_model_used = "Heuristic Baseline"

        # 4. Gọi Gemini-3-Flash LLM để tổng hợp ngữ cảnh (Context Synthesis & Gherkin ACs)
        if self.llm_service and self.llm_service.is_available():
            llm_result = self.llm_service.synthesize_task(
                task_input=task_input,
                similar_tasks=similar_tasks,
                baseline_estimate=suggested_hours
            )
            if llm_result:
                if llm_result.get("standardized_title"):
                    standardized_title = llm_result["standardized_title"]
                if llm_result.get("acceptance_criteria") and len(llm_result["acceptance_criteria"]) > 0:
                    acceptance_criteria = llm_result["acceptance_criteria"]
                if "estimated_hours" in llm_result and llm_result["estimated_hours"]:
                    suggested_hours = float(llm_result["estimated_hours"])
                    story_points = self._hours_to_story_points(suggested_hours)
                technical_reasoning = llm_result.get("technical_reasoning", technical_reasoning)
                llm_model_used = llm_result.get("llm_model", "Gemini-3-Flash")

        if is_duplicate:
            flag_status = "WARNING_DUPLICATE"
            flag_reason = f"Trùng lặp cao ({round(similar_tasks[0]['similarity_score']*100, 1)}%) với ticket {duplicate_with}"
        elif len(description) < 10 and not tech_stack:
            flag_status = "NEEDS_INPUT"
            flag_reason = "Thiếu thông tin chi tiết / tech stack, cần Dev bổ sung input"
        else:
            flag_status = "READY_TO_IMPORT"
            flag_reason = f"Đã chuẩn hoá format và AC bởi {llm_model_used}, đối chiếu {len(top_match_info)} ticket quá khứ"

        return {
            "source_row": task_input.get("row_index", 1),
            "original_title": raw_title,
            "standardized_title": standardized_title,
            "module": module,
            "task_type": task_type,
            "description": description,
            "tech_stack": tech_stack,
            "priority": task_input.get("priority", "Medium"),
            "estimated_hours": suggested_hours,
            "story_points": story_points,
            "acceptance_criteria": acceptance_criteria,
            "technical_reasoning": technical_reasoning,
            "llm_model": llm_model_used,
            "similar_historical_tasks": top_match_info,
            "flag_status": flag_status,
            "flag_reason": flag_reason,
            "is_approved": (flag_status == "READY_TO_IMPORT")
        }
