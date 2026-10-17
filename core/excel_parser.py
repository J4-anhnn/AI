"""
Module: core/excel_parser.py
Step A in Diagram: Information Extraction from Excel (Raw Data Sources)
Trích xuất dữ liệu thô từ file Excel của Dev/BA thành dạng dữ liệu có cấu trúc.
Hỗ trợ cả tiếng Anh, tiếng Việt, đa sheet, xử lý lỗi header linh hoạt.
"""

import os
import re
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np


class ExcelTaskParser:
    """
    Parser thông minh trích xuất User Stories / Tasks / Dev Specs từ file Excel.
    Chuẩn hoá các cột dữ liệu không đồng nhất từ nhiều Dev khác nhau.
    """

    COLUMN_MAPPINGS = {
        "ticket_key": ["ticket_key", "ticket_id", "key", "id", "jira_id", "mã ticket"],
        "task_type": ["task_type", "suggested_type", "type", "loại task", "scope", "vai trò"],
        "module": ["module", "feature_name", "feature", "chức năng", "phân hệ", "epic", "component"],
        "title": ["title", "raw_dev_task", "task_name", "task title", "tên task", "tên công việc", "summary", "tên yêu cầu", "công việc", "task"],
        "description": ["description", "dev_notes", "mô tả", "ghi chú", "chi tiết", "details", "acceptance criteria", "ghi chú kỹ thuật", "note"],
        "estimated_hours": ["estimated_hours", "estimate", "thời gian dự kiến", "hours", "giờ ước tính", "est_hours", "time"],
        "actual_hours": ["actual_hours", "actual", "thực tế", "giờ thực tế", "spent_hours", "spent"],
        "story_points": ["story_points", "sp", "points", "điểm story"],
        "priority": ["priority", "độ ưu tiên", "mức độ", "urgency"],
        "tech_stack": ["tech_stack", "công nghệ", "stack", "technology", "ngôn ngữ"]
    }

    def __init__(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File Excel không tồn tại: {file_path}")
        self.file_path = file_path
        self.excel_file = pd.ExcelFile(file_path)

    def get_sheet_names(self) -> List[str]:
        return self.excel_file.sheet_names

    def _match_column(self, col_name: str, used_keys: set) -> Optional[str]:
        clean_col = re.sub(r"[\s_\-]+", " ", str(col_name).strip().lower())
        
        # Priority 1: Exact matches
        for standard_key, variations in self.COLUMN_MAPPINGS.items():
            if standard_key in used_keys:
                continue
            for var in variations:
                clean_var = re.sub(r"[\s_\-]+", " ", var.strip().lower())
                if clean_var == clean_col:
                    return standard_key

        # Priority 2: Word boundary regex matches
        for standard_key, variations in self.COLUMN_MAPPINGS.items():
            if standard_key in used_keys:
                continue
            for var in variations:
                clean_var = re.sub(r"[\s_\-]+", " ", var.strip().lower())
                pattern = r"\b" + re.escape(clean_var) + r"\b"
                if re.search(pattern, clean_col):
                    return standard_key

        return None

    @staticmethod
    def _safe_get_scalar(val: Any) -> Any:
        if isinstance(val, pd.Series):
            return val.iloc[0] if len(val) > 0 else ""
        if isinstance(val, (np.ndarray, list)):
            return val[0] if len(val) > 0 else ""
        return val

    def parse_sheet(self, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
        target_sheet = sheet_name or self.excel_file.sheet_names[0]
        df = pd.read_excel(self.file_path, sheet_name=target_sheet)

        matched_columns = {}
        used_keys = set()
        for col in df.columns:
            matched = self._match_column(str(col), used_keys)
            if matched:
                matched_columns[col] = matched
                used_keys.add(matched)

        df_mapped = df.rename(columns=matched_columns)

        tasks = []
        for index, row in df_mapped.iterrows():
            if row.isna().all():
                continue

            raw_title_val = self._safe_get_scalar(row.get("title", ""))
            title = ""
            if pd.notna(raw_title_val):
                title = str(raw_title_val).strip()
            if not title or title.lower() == "nan":
                raw_desc_val = self._safe_get_scalar(row.get("description", ""))
                if pd.notna(raw_desc_val):
                    d_str = str(raw_desc_val).strip()
                    if d_str and d_str.lower() != "nan":
                        title = d_str[:60] + "..." if len(d_str) > 60 else d_str
                if not title:
                    continue

            raw_desc = self._safe_get_scalar(row.get("description", ""))
            description = str(raw_desc).strip() if pd.notna(raw_desc) and str(raw_desc).lower() != "nan" else ""

            raw_mod = self._safe_get_scalar(row.get("module", "General"))
            module = str(raw_mod).strip() if pd.notna(raw_mod) and str(raw_mod).lower() != "nan" else "General"

            raw_type = self._safe_get_scalar(row.get("task_type", "Backend"))
            task_type = str(raw_type).strip() if pd.notna(raw_type) and str(raw_type).lower() != "nan" else "Backend"

            raw_prio = self._safe_get_scalar(row.get("priority", "Medium"))
            priority = str(raw_prio).strip() if pd.notna(raw_prio) and str(raw_prio).lower() != "nan" else "Medium"

            raw_tech = self._safe_get_scalar(row.get("tech_stack", ""))
            tech_stack = str(raw_tech).strip() if pd.notna(raw_tech) and str(raw_tech).lower() != "nan" else ""

            raw_est = self._safe_get_scalar(row.get("estimated_hours", 0.0))
            try:
                estimated_hours = float(raw_est) if pd.notna(raw_est) else 0.0
            except (ValueError, TypeError):
                estimated_hours = 0.0

            raw_act = self._safe_get_scalar(row.get("actual_hours", estimated_hours))
            try:
                actual_hours = float(raw_act) if pd.notna(raw_act) else estimated_hours
            except (ValueError, TypeError):
                actual_hours = estimated_hours

            raw_sp = self._safe_get_scalar(row.get("story_points", 0))
            try:
                story_points = int(raw_sp) if pd.notna(raw_sp) else 0
            except (ValueError, TypeError):
                story_points = 0

            raw_ticket = self._safe_get_scalar(row.get("ticket_key", f"ROW-{index+1}"))
            ticket_key = str(raw_ticket).strip() if pd.notna(raw_ticket) else f"ROW-{index+1}"

            raw_dict = {}
            for k, v in row.to_dict().items():
                scalar_v = self._safe_get_scalar(v)
                raw_dict[k] = None if pd.isna(scalar_v) else scalar_v

            task_item = {
                "row_index": index + 1,
                "sheet_name": target_sheet,
                "ticket_key": ticket_key,
                "module": module,
                "title": title,
                "description": description,
                "task_type": task_type,
                "estimated_hours": estimated_hours,
                "actual_hours": actual_hours,
                "story_points": story_points,
                "priority": priority,
                "tech_stack": tech_stack,
                "raw_data": raw_dict
            }
            tasks.append(task_item)

        return tasks
