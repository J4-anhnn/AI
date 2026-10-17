"""
Module: core/chunker.py
Step B in Diagram: Chunking & Semantic Structuring
Biến đổi các dòng task từ Excel thành các Chunks có ngữ nghĩa giàu metadata
để tối ưu hoá việc Vector Embedding và RAG Retrieval.
"""

import re
from typing import List, Dict, Any


class TaskChunker:
    """
    Chịu trách nhiệm phân mảnh ngữ nghĩa (Semantic Chunking) cho các đầu việc Dev / User Story.
    Tạo ra format văn bản tối ưu hóa cho Vector Search.
    """

    @staticmethod
    def create_semantic_chunk(task_dict: Dict[str, Any], is_historical: bool = True) -> Dict[str, Any]:
        """
        Gộp các trường thông tin (Title, Module, Type, Tech Stack, Description)
        thành đoạn văn bản hoàn chỉnh biểu thị ngữ cảnh đầy đủ của task.
        """
        module = task_dict.get("module", "General")
        task_type = task_dict.get("task_type", "Backend")
        title = task_dict.get("title", "")
        description = task_dict.get("description", "")
        tech_stack = task_dict.get("tech_stack", "")

        # Xây dựng semantic text để embedding nắm bắt được ngữ cảnh kỹ thuật
        parts = [
            f"Module: {module}",
            f"Type: {task_type}",
            f"Task: {title}"
        ]
        if tech_stack:
            parts.append(f"Tech: {tech_stack}")
        if description:
            parts.append(f"Details: {description}")

        semantic_content = " | ".join(parts)

        chunk_id = f"{task_dict.get('ticket_key', 'TASK')}-chunk-0"

        return {
            "chunk_id": chunk_id,
            "text": semantic_content,
            "title": title,
            "module": module,
            "task_type": task_type,
            "tech_stack": tech_stack,
            "description": description,
            "is_historical": is_historical,
            "estimated_hours": float(task_dict.get("estimated_hours", 0.0)),
            "actual_hours": float(task_dict.get("actual_hours", 0.0)),
            "story_points": int(task_dict.get("story_points", 0)),
            "priority": task_dict.get("priority", "Medium"),
            "ticket_key": task_dict.get("ticket_key", ""),
            "metadata": {
                "source_row": task_dict.get("row_index", 0),
                "sheet": task_dict.get("sheet_name", ""),
                "prefix": task_dict.get("prefix", f"[{task_type.upper()}][{module.upper()}]")
            }
        }

    @staticmethod
    def chunk_unstructured_requirement(feature_name: str, raw_text: str) -> List[Dict[str, Any]]:
        """
        Dành cho trường hợp Dev/BA viết 1 đoạn văn dài nhiều gạch đầu dòng trong 1 ô Excel.
        Hàm này sẽ tách thành các sub-task logic riêng biệt.
        """
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        chunks = []
        for idx, line in enumerate(lines):
            # Lọc bỏ dấu gạch đầu dòng -, *, 1.
            clean_line = re.sub(r"^[\-*•\d\.\)]+\s*", "", line)
            if len(clean_line) < 5:
                continue

            chunks.append({
                "chunk_id": f"subtask-{idx+1}",
                "text": f"Feature: {feature_name} | Subtask: {clean_line}",
                "title": clean_line,
                "module": feature_name,
                "task_type": "Auto-Detect",
                "tech_stack": "",
                "description": clean_line,
                "is_historical": False,
                "estimated_hours": 0.0,
                "actual_hours": 0.0,
                "story_points": 0,
                "priority": "Medium",
                "ticket_key": f"REQ-{idx+1}",
                "metadata": {"auto_generated": True}
            })
        return chunks
