"""拍摄进度业务规则：状态流转、字段校验与筛选口径都收在这里。

约定：
- pending/abnormal 一律由 status 派生，申请顺延中断、重试都不会留下脏标记；
- 业务字段缺失或读不到时统一显示「暂无」，列表、详情、导出、概览共用同一口径；
- 已收工是终态，重试只处理未完成拍摄日，已有的收工结果（完成场次等）不被覆盖。
"""
from __future__ import annotations

from typing import Any


def _repo():
    """延迟取仓库单例：store 初始化时会回调本模块，顶层直接 import 会循环。"""
    from app.store import store

    return store

MODULE = "shooting"
REQUIRED_FIELDS = ["拍摄日编号", "拍摄日期", "拍摄地点"]
OPTIONAL_FIELDS = ["计划场次", "完成场次", "有效工时", "超时情况"]
DISPLAY_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
EMPTY_PLACEHOLDER = "暂无"

STATUS_ORDER = ["待拍摄", "拍摄中", "已收工", "已顺延"]
DONE_STATUS = "已收工"
ABNORMAL_STATUS = "已顺延"
ACTION_RULES = {"开始拍摄": "拍摄中", "确认收工": "已收工", "申请顺延": "已顺延"}
# 允许的流转方向：已收工为终态不允许再操作；已顺延可重新开拍。
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "待拍摄": {"开始拍摄", "申请顺延"},
    "拍摄中": {"确认收工", "申请顺延"},
    "已顺延": {"开始拍摄"},
    "已收工": set(),
}


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """把一条拍摄日规整成统一口径：空值显示「暂无」，派生标记按状态重算。

    列表、详情、导出、概览和动作返回都走这里，避免各端保留旧值。
    """
    for field in DISPLAY_FIELDS:
        value = entry.get(field)
        text = str(value).strip() if value is not None else ""
        entry[field] = text if text else EMPTY_PLACEHOLDER
    status = str(entry.get("status") or "").strip()
    if status not in STATUS_ORDER:
        # 读到残缺/非法状态时回到待拍摄，绝不沿用上一条的完成状态。
        status = STATUS_ORDER[0]
    entry["status"] = status
    entry["拍摄状态"] = status
    entry["pending"] = status != DONE_STATUS
    entry["abnormal"] = status == ABNORMAL_STATUS
    return entry


class ShootingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [normalize_entry(dict(row)) for row in _repo().rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("拍摄日编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = _repo().find(MODULE, entry_id)
        return normalize_entry(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = _repo().rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in DISPLAY_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        rows.append(entry)
        return normalize_entry(dict(entry)), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str, bool]:
        """执行状态流转，返回 (记录, 说明, 是否真的发生了更新)。

        重复提交同一动作时按幂等处理：已经在目标状态就不再改写，保证中断后
        重试不会把已完成/已顺延的拍摄日又拨回旧进度。
        """
        action = action.strip()
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于拍摄进度可执行范围", False
        entry = _repo().find(MODULE, entry_id)
        if entry is None:
            return None, f"拍摄日 {entry_id} 不存在或已归档", False
        normalize_entry(entry)
        target = ACTION_RULES[action]
        current = str(entry["status"])
        if current == DONE_STATUS:
            # 终态一律拦截，包括重复收工，保证收工结果不被任何重试改写。
            return None, f"拍摄日已收工，收工结果保留，不再执行「{action}」", False
        if current == target:
            return normalize_entry(dict(entry)), f"拍摄日已是「{target}」状态，无需重复{action}", False
        if action not in ALLOWED_TRANSITIONS.get(current, set()):
            return None, f"拍摄日当前为「{current}」，不能执行「{action}」", False
        entry["status"] = target
        normalize_entry(entry)
        return normalize_entry(dict(entry)), f"拍摄日已{action}", True

    def retry_pending(self) -> dict[str, int]:
        """中断后的批量重试：只规整未完成拍摄日，已收工记录原样保留。"""
        updated = 0
        skipped = 0
        for entry in _repo().rows(MODULE):
            normalize_entry(entry)
            if entry["pending"]:
                updated += 1
            else:
                skipped += 1
        return {"updated": updated, "skipped": skipped}

    def stats(self) -> dict[str, int]:
        """与概览同口径的数量统计，供列表页卡片直接展示。"""
        planned = completed = postponed = 0
        for entry in _repo().rows(MODULE):
            normalize_entry(entry)
            planned += 1
            if entry["status"] == DONE_STATUS:
                completed += 1
            elif entry["status"] == ABNORMAL_STATUS:
                postponed += 1
        return {"planned": planned, "completed": completed, "postponed": postponed}
