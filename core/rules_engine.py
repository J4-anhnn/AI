"""
Module: core/rules_engine.py
Hỗ trợ Step 1 & Step 4:
- Step 1: Define Standard Input mà AI có thể đọc được (Context, Minimum Input, Rules theo GSD / Super Power)
- Step 4: Tự động sinh ra bộ Rules File (.agent-rules.md hoặc project_rules.json) độc lập,
  đảm bảo chỉ áp dụng cho Project này, KHÔNG làm ảnh hưởng đến các session chat khác!
"""

import json
import os
from typing import Dict, Any, List


class StandardRulesEngine:
    """
    Quản lý bộ quy chuẩn Input chuẩn hóa (Standard Input Schema)
    và sinh File Rules biệt lập cho Project.
    """

    DEFAULT_STANDARD_INPUT_SCHEMA = {
        "context": {
            "project_name": "AI Jira/ADO Task Breakdown & Estimation Engine",
            "repository": "/Users/user/Documents/AI",
            "tech_stack": ["Python", "FastAPI/Flask", "React", "PostgreSQL", "Redis", "Docker"],
            "jira_project_key": "PROJ",
            "ado_area_path": "Project\\Core"
        },
        "minimum_required_fields": [
            {
                "field": "title / raw_dev_task",
                "description": "Tên công việc hoặc câu tóm tắt hành động dev cần làm",
                "example": "Làm chức năng bật tắt 2FA bằng Google Authenticator"
            },
            {
                "field": "module / feature_name",
                "description": "Phân hệ nghiệp vụ của task",
                "example": "Authentication"
            },
            {
                "field": "dev_notes / description",
                "description": "Ghi chú kỹ thuật, API, bảng DB, thư viện sử dụng (tối thiểu 15 ký tự)",
                "example": "Dùng pyotp sinh QR TOTP, verify 6 số otp, lưu secret AES vào Postgres"
            },
            {
                "field": "suggested_type",
                "description": "Phân loại: Backend, Frontend, Database, QA, DevOps",
                "example": "Backend"
            }
        ],
        "naming_rules": {
            "format": "[{TYPE}][{MODULE}] {Action in imperative mood}",
            "type_prefixes": {
                "Backend": "[BE]",
                "Frontend": "[FE]",
                "Database": "[DB]",
                "QA/Testing": "[QA]",
                "DevOps": "[DEVOPS]"
            },
            "examples": [
                "[BE][AUTH] Implement TOTP verification endpoint",
                "[FE][AUTH] Build 2FA QR code scanner modal",
                "[DB][PAYMENT] Add migration for payment_transactions"
            ]
        },
        "estimation_rules": {
            "scale": "Fibonacci (1, 2, 3, 5, 8, 13, 21)",
            "max_hours_per_task": 16.0,
            "subtask_splitting_threshold": 16.0,
            "weighted_similarity_source": "historical_dev_backlog.xlsx"
        }
    }

    @classmethod
    def generate_project_rules_markdown(cls, custom_config: Dict[str, Any] = None) -> str:
        """
        Sinh file .agent-rules.md độc lập cho Agent IDE/CLI.
        Sử dụng cấu trúc GSD (Get Stuff Done) & Super Power chuẩn quốc tế:
        Có frontmatter scope rõ ràng để không impact sang các project khác!
        """
        cfg = custom_config or cls.DEFAULT_STANDARD_INPUT_SCHEMA

        content = f"""---
# SCOPE BOUNDARY (Chỉ kích hoạt khi làm việc với thư mục này)
project_name: "{cfg['context']['project_name']}"
root_directory: "{cfg['context']['repository']}"
jira_key: "{cfg['context']['jira_project_key']}"
active: true
isolation_level: "strict_project_only"
---

# PROJECT AI RULES: TASK BREAKDOWN & ESTIMATION STANDARD (GSD SPEC)

> **Mục tiêu:** Tự động hoá việc đọc Excel của Dev, vector hoá ngữ cảnh lịch sử, chuẩn hoá naming convention và estimate giờ làm việc trước khi log lên Jira/ADO.

---

## 1. MINIMUM INPUT SPECIFICATION (Chuẩn đầu vào từ Dev)
Khi đọc file Excel từ Dev, Agent PHẢI đảm bảo các cột sau có dữ liệu hợp lệ:
1. `raw_dev_task`: Động từ hành động rõ ràng.
2. `module`: Phân hệ cụ thể (Auth, Payment, Search, Notification, DevOps, QA...).
3. `dev_notes`: Chi tiết kỹ thuật (API endpoint, Thư viện, DB table). Nếu dưới 15 ký tự -> Flag `NEEDS_INPUT`.
4. `suggested_type`: Backend | Frontend | Database | QA | DevOps.

---

## 2. STRICT NAMING CONVENTION (Quy ước đặt tên Task)
Mọi task được tạo ra BẮT BUỘC theo cú pháp:
`[{{TYPE}}][{{MODULE}}] <Hành động kỹ thuật>`

Bảng tiền tố chuẩn:
- Backend: `[BE][MODULE]`
- Frontend: `[FE][MODULE]`
- Database / Migration: `[DB][MODULE]`
- Quality Assurance / Automation: `[QA][MODULE]`
- Infrastructure / CI/CD: `[DEVOPS][MODULE]`

*Ví dụ chuẩn:*
- `[BE][AUTH] Implement TOTP QR code generator endpoint`
- `[FE][AUTH] 2FA OTP 6-digit input form component`
- `[DB][PAYMENT] Add migration for MoMo transaction logs`

---

## 3. RAG ESTIMATION & HISTORICAL VECTOR BENCHMARK
1. Agent PHẢI tra cứu vector tương đồng trong Vector DB (`historical_dev_backlog.xlsx`).
2. Giờ ước tính được tính theo trọng số Cosine Similarity:
   `Estimated_Hours = Sum(Sim_i * Actual_Hours_i) / Sum(Sim_i)`
3. Quy đổi Story Points theo Fibonacci:
   - <= 4h: 1 SP
   - 5 - 7h: 2 SP
   - 8 - 11h: 3 SP
   - 12 - 16h: 5 SP
   - > 16h: BẮT BUỘC tách thành 2 subtasks!
4. Nếu độ tương đồng với ticket cũ >= 85%: Bắt buộc đánh cờ `WARNING_DUPLICATE`.

---

## 4. JIRA & ADO IMPORT GUARDRAILS (Phase 2 Review)
1. Chỉ đẩy lên Jira/ADO khi: `flag_status == "READY_TO_IMPORT"` VÀ `is_approved == true`.
2. Giữ lại các task `NEEDS_INPUT` hoặc `WARNING_DUPLICATE` trong danh sách để Dev chỉnh sửa.
3. Không tự ý log ticket khi chưa có xác nhận duyệt từ Human.
"""
        return content

    @classmethod
    def save_rules_file(cls, output_path: str = "/Users/user/Documents/AI/.agent-rules.md"):
        content = cls.generate_project_rules_markdown()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path
