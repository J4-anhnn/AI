"""
Module: core/llm_service.py
LLM Integration Service: Gemini-3-Flash
Cung cấp khả năng suy luận ngữ cảnh sâu (Context Synthesis),
chuẩn hóa Naming convention, tạo tiêu chí nghiệm thu Acceptance Criteria (Gherkin style),
và lập luận kỹ thuật (Technical Reasoning) dựa trên dữ liệu RAG.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from openai import OpenAI


class GeminiFlashLLM:
    """
    Client kết nối tới mô hình Gemini-3-Flash thông qua OpenAI SDK interface.
    """

    DEFAULT_BASE_URL = os.environ.get(
        "LLM_BASE_URL",
        "https://aiportalapi.stu-platform.live/jpe"
    )
    DEFAULT_API_KEY = os.environ.get(
        "LLM_API_KEY",
        "sk-nLkexsHhayST-zLiArKwBg"
    )
    DEFAULT_MODEL = os.environ.get(
        "LLM_MODEL",
        "Gemini-3-Flash"
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.model = model or self.DEFAULT_MODEL
        self.client: Optional[OpenAI] = None
        self._init_client()

    def _init_client(self):
        try:
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key
            )
        except Exception as e:
            print(f"[GeminiFlashLLM Error] Không thể khởi tạo OpenAI client: {e}")
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None and bool(self.api_key)

    def synthesize_task(
        self,
        task_input: Dict[str, Any],
        similar_tasks: List[Dict[str, Any]],
        baseline_estimate: float
    ) -> Optional[Dict[str, Any]]:
        """
        Gọi mô hình Gemini-3-Flash để phân tích task với bối cảnh RAG từ ticket lịch sử.
        """
        if not self.is_available():
            return None

        # Format historical benchmark context
        benchmarks_str = ""
        for i, m in enumerate(similar_tasks[:3], 1):
            benchmarks_str += (
                f"  {i}. [{m.get('ticket_key')}] {m.get('title')}\n"
                f"     - Actual Hours: {m.get('actual_hours', 0)}h | Story Points: {m.get('story_points', 0)}\n"
                f"     - Similarity: {m.get('relevance_percent', 0)}%\n"
                f"     - Tech Stack: {m.get('tech_stack', 'N/A')}\n"
            )

        if not benchmarks_str:
            benchmarks_str = "  (Không có ticket quá khứ tương đồng)\n"

        prompt = f"""Bạn là AI Senior Tech Lead kiêm Scrum Master chuyên nghiệp trong hệ thống RAG Task Breakdown.
Hãy phân tích yêu cầu sau từ file Excel của Dev:

[YÊU CẦU MỚI TỪ DEV]
- Tiêu đề thô: {task_input.get('title', 'N/A')}
- Phân hệ (Module): {task_input.get('module', 'General')}
- Phân loại (Type): {task_input.get('task_type', 'Backend')}
- Tech Stack: {task_input.get('tech_stack', 'N/A')}
- Ghi chú kỹ thuật (Dev Notes): {task_input.get('description', 'N/A')}

[DỮ LIỆU ĐỐI CHỨNG LỊCH SỬ (VECTOR RETRIEVAL BENCHMARKS)]
{benchmarks_str}
- Baseline Giờ Ước lượng (Toán học RAG): {baseline_estimate} giờ

[QUY TẮC BẮT BUỘC]
1. Chuẩn hóa Naming: Bắt buộc theo định dạng [TYPE][MODULE] <Hành động kỹ thuật rõ ràng>.
   (Ví dụ: [BE][AUTH] Implement TOTP QR code generator, [FE][PAYMENT] Checkout modal...)
2. Acceptance Criteria: Sinh đúng 3 tiêu chí nghiệm thu rõ ràng theo chuẩn Gherkin (Given... When... Then...).
3. Ước lượng giờ (Estimated Hours): Xem xét baseline {baseline_estimate}h và độ phức tạp kỹ thuật của task để đưa ra số giờ thực tế hợp lý.
4. Story Points: Quy đổi theo dãy Fibonacci (1, 2, 3, 5, 8, 13, 21). Nếu > 16h, đề xuất tách nhỏ.
5. Lập luận kỹ thuật (Technical Reasoning): Giải thích ngắn gọn (2-3 câu) vì sao cần số giờ này dựa trên đối chiếu ticket cũ.

BẮT BUỘC TRẢ VỀ DUY NHẤT ĐỊNH DẠNG JSON HỢP LỆ (KHÔNG markdown, KHÔNG kèm giải thích ngoài JSON):
{{
  "standardized_title": "...",
  "estimated_hours": 8.0,
  "story_points": 3,
  "acceptance_criteria": [
    "Given ... when ... then ...",
    "Given ... when ... then ...",
    "Given ... when ... then ..."
  ],
  "technical_reasoning": "..."
}}
"""

        try:
            resp = self.client.responses.create(
                model=self.model,
                input=prompt
            )

            raw_text = getattr(resp, "output_text", "")
            if not raw_text and hasattr(resp, "output"):
                # Fallback trích xuất từ structure output nếu có
                try:
                    raw_text = resp.output[0].content[0].text
                except Exception:
                    raw_text = str(resp)

            # Làm sạch JSON nếu model bọc trong ```json
            cleaned_json = raw_text.strip()
            if "```" in cleaned_json:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_json)
                if match:
                    cleaned_json = match.group(1).strip()

            data = json.loads(cleaned_json)
            return {
                "standardized_title": data.get("standardized_title"),
                "estimated_hours": float(data.get("estimated_hours", baseline_estimate)),
                "story_points": int(data.get("story_points", 3)),
                "acceptance_criteria": data.get("acceptance_criteria", []),
                "technical_reasoning": data.get("technical_reasoning", ""),
                "llm_model": self.model
            }
        except Exception as e:
            print(f"[GeminiFlashLLM Inference Error] Lỗi khi gọi model {self.model}: {e}")
            return None
