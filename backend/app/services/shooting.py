"""拍摄进度业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "shooting"
REQUIRED_FIELDS = ["拍摄日编号", "拍摄日期", "拍摄地点"]
PROGRESS_FIELDS = ["计划场次", "完成场次", "有效工时", "超时情况"]
STATUS_FIELD = "拍摄状态"
EMPTY_PLACEHOLDER = "暂无"
STATUS_ORDER = ["待拍摄", "拍摄中", "已收工", "已顺延"]
TERMINAL_STATUSES = {"已收工", "已顺延"}
ACTION_RULES = {"开始拍摄": "拍摄中", "确认收工": "已收工", "申请顺延": "已顺延"}
NEGATIVE_ACTIONS = []


class ShootingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("拍摄日编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 进度字段缺省时显式写成「暂无」，避免详情接口缺字段、列表残留旧值
        for field in PROGRESS_FIELDS:
            value = str(values.get(field) or "").strip()
            entry[field] = value or EMPTY_PLACEHOLDER
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"拍摄日 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于拍摄进度可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current = str(entry.get("status") or "")
        if current in TERMINAL_STATUSES:
            # 已收工、已顺延的拍摄日不再改写；中断后重试同一动作按幂等成功处理
            if current == target:
                return entry, f"拍摄日{current}，「{action}」无需重复执行"
            return None, f"拍摄日{current}，不能再执行「{action}」"
        entry["status"] = target
        entry[STATUS_FIELD] = target
        entry["pending"] = target not in TERMINAL_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"拍摄日已{action}"
