"""
Module: core/jira_ado_service.py
Phase 1 & Phase 2:
- Review & Flagging: Phân loại task có thể import (Ready) và task lỗi cần sửa (Failed/Needs review)
- Jira & Azure DevOps (ADO) API Payload Generator & Import Execution
- Hỗ trợ chọn lọc (Select / Deselect) từng task để import
"""

import json
import time
from typing import List, Dict, Any, Optional


class JiraAdoIntegrationService:
    """
    Dịch vụ kết nối và đồng bộ Task lên Jira Cloud và Azure DevOps (ADO).
    """

    @staticmethod
    def build_jira_payload(task: Dict[str, Any], project_key: str = "PROJ") -> Dict[str, Any]:
        """Tạo payload chuẩn Atlassian Jira REST API v3"""
        ac_lines = task.get("acceptance_criteria", [])
        ac_text = "\n* " + "\n* ".join(ac_lines) if ac_lines else "None"

        full_description = (
            f"h3. Task Details\n"
            f"{task.get('description', 'N/A')}\n\n"
            f"*Module:* {task.get('module')}\n"
            f"*Tech Stack:* {task.get('tech_stack', 'N/A')}\n\n"
            f"h3. Acceptance Criteria (Gherkin)\n"
            f"{ac_text}\n\n"
            f"h3. AI Vector & LLM Reasoning\n"
            f"*Model:* {task.get('llm_model', 'Gemini-3-Flash')}\n"
            f"*Estimate:* {task.get('estimated_hours', 0)}h ({task.get('story_points', 0)} Story Points)\n"
            f"*Technical Reasoning:* {task.get('technical_reasoning', 'Estimated by historical vector RAG.')}"
        )

        return {
            "fields": {
                "project": {"key": project_key},
                "summary": task.get("standardized_title", "Untitled Task"),
                "description": full_description,
                "issuetype": {"name": "Task"},
                "priority": {"name": task.get("priority", "Medium")},
                "timetracking": {
                    "originalEstimate": f"{task.get('estimated_hours', 4)}h",
                    "remainingEstimate": f"{task.get('estimated_hours', 4)}h"
                },
                "customfield_story_points": task.get("story_points", 1),
                "labels": [
                    task.get("module", "general").lower(),
                    task.get("task_type", "task").lower(),
                    "gemini-3-flash",
                    "ai-generated"
                ]
            }
        }

    @staticmethod
    def build_ado_payload(task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Tạo payload JSON Patch chuẩn Azure DevOps Work Items API"""
        ac_html = "<ul>" + "".join([f"<li>{item}</li>" for item in task.get("acceptance_criteria", [])]) + "</ul>"

        desc_html = (
            f"<div>"
            f"<p><strong>Description:</strong> {task.get('description', '')}</p>"
            f"<p><strong>Module:</strong> {task.get('module')}</p>"
            f"<p><strong>Tech:</strong> {task.get('tech_stack', '')}</p>"
            f"<p><strong>LLM Model:</strong> {task.get('llm_model', 'Gemini-3-Flash')}</p>"
            f"<p><strong>Reasoning:</strong> {task.get('technical_reasoning', 'N/A')}</p>"
            f"<hr/>"
            f"<p><strong>Acceptance Criteria (Gherkin):</strong></p>"
            f"{ac_html}"
            f"</div>"
        )

        return [
            {"op": "add", "path": "/fields/System.Title", "value": task.get("standardized_title", "")},
            {"op": "add", "path": "/fields/System.Description", "value": desc_html},
            {"op": "add", "path": "/fields/System.AreaPath", "value": f"Project\\{task.get('module', 'General')}"},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.OriginalEstimate", "value": float(task.get("estimated_hours", 4))},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints", "value": int(task.get("story_points", 1))},
            {"op": "add", "path": "/fields/System.Tags", "value": f"AI-Generated; {task.get('module')}; {task.get('task_type')}"}
        ]

    @classmethod
    def execute_import(
        cls,
        tasks: List[Dict[str, Any]],
        target_platform: str = "Jira",
        project_key: str = "PROJ"
    ) -> Dict[str, Any]:
        """
        Thực hiện bắn các task đã approve lên Jira hoặc ADO.
        Tách biệt rõ:
        - Thành công: Sinh ticket key (PROJ-201, PROJ-202...)
        - Thất bại / Giữ lại: Các task bị warning hoặc chưa approve
        """
        imported_tickets = []
        failed_or_skipped = []

        counter = 201
        for idx, task in enumerate(tasks):
            # Chỉ import nếu user đã tick approve và task ở trạng thái Ready
            if not task.get("is_approved", False) or task.get("flag_status") != "READY_TO_IMPORT":
                failed_or_skipped.append({
                    "task_title": task.get("standardized_title") or task.get("original_title"),
                    "reason": task.get("flag_reason", "Chưa được duyệt hoặc thiếu thông tin"),
                    "status": task.get("flag_status", "NEEDS_INPUT")
                })
                continue

            # Giả lập call API thực tế lên Jira/ADO
            mock_ticket_id = f"{project_key}-{counter}" if target_platform == "Jira" else f"ADO-{counter * 10}"
            counter += 1

            if target_platform == "Jira":
                payload = cls.build_jira_payload(task, project_key=project_key)
            else:
                payload = cls.build_ado_payload(task)

            imported_tickets.append({
                "ticket_key": mock_ticket_id,
                "title": task.get("standardized_title"),
                "module": task.get("module"),
                "task_type": task.get("task_type"),
                "estimated_hours": task.get("estimated_hours"),
                "story_points": task.get("story_points"),
                "target_platform": target_platform,
                "api_endpoint": f"https://your-company.atlassian.net/rest/api/3/issue/{mock_ticket_id}" if target_platform == "Jira" else f"https://dev.azure.com/org/project/_workitems/edit/{mock_ticket_id}",
                "payload": payload,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })

        return {
            "success_count": len(imported_tickets),
            "skipped_count": len(failed_or_skipped),
            "target_platform": target_platform,
            "imported_tickets": imported_tickets,
            "retained_tasks": failed_or_skipped
        }
