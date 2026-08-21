"""任务计时台账 —— 测试阶段监控用（用户要求：能在 API 文档里监控到）。

每个后台任务（嵌字 / 书页翻译）在阶段边界"打卡"，计时数据存两处：
  内存台账：GET /api/monitor 实时看（API 文档里），重启后端清空
  磁盘日志：data/render_times.log 每跑完一次追加一行，重启也不丢（历史留底）

计时本身开销微秒级（time.time() 读一次系统时钟），跟动辄几十秒的任务比
完全可以忽略，不会拖慢程序。
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

from ..config import DATA_DIR

_LOG_FILE = DATA_DIR / "render_times.log"

# 内存台账：image_id -> 最新一次运行的记录。
# 后台任务在独立线程里跑，两个任务同时打卡会打架——加把锁管秩序
# （同款思路见 db.py 的 Session：共享资源要有人管秩序）
_lock = threading.Lock()
_records: dict[int, dict] = {}


def start_task(image_id: int, kind: str) -> None:
    """任务开始：立一张台账卡。kind = "嵌字" / "书页翻译"（给人看的名字）。"""
    with _lock:
        _records[image_id] = {
            "image_id": image_id,
            "kind": kind,
            "started_at": _now(),
            "_t0": time.time(),          # 内部起跑时间戳，算秒数用
            "finished_at": None,
            "status": "running",
            "stages": [],                # [{"stage": 阶段名, "seconds": 累计秒数}]
            "total_seconds": None,
        }


def checkpoint(image_id: int, stage: str) -> None:
    """阶段边界打卡：刚跑完一个阶段，记一行"从起跑到现在用了多少秒"。
    阶段名是中文，直接给人看。任务跑着的时候轮询 /api/monitor，
    就能看到秒数一节节涨。"""
    with _lock:
        rec = _records.get(image_id)
        if not rec or rec["status"] != "running":
            return
        rec["stages"].append({
            "stage": stage,
            "seconds": round(time.time() - rec["_t0"], 1),
        })


def end_task(image_id: int, status: str) -> None:
    """任务结束：封台账卡 + 追加一行到磁盘日志（重启也不丢的留底）。"""
    with _lock:
        rec = _records.get(image_id)
        if not rec:
            return
        rec["status"] = status
        rec["finished_at"] = _now()
        rec["total_seconds"] = round(time.time() - rec["_t0"], 1)
        _write_log(rec)


def elapsed_seconds(image_id: int) -> float | None:
    """任务从起跑到现在过了多少秒（跑完的返回总耗时，没记录的返回 None）。
    给 result 接口用：用户每次刷新都能看到"已经过去多长时间"，
    复制 JSON 时时间信息也跟着走。"""
    with _lock:
        rec = _records.get(image_id)
        if not rec:
            return None
        if rec["status"] == "running":
            return round(time.time() - rec["_t0"], 1)
        return rec["total_seconds"]


def list_records() -> list[dict]:
    """给 /api/monitor 用：所有台账卡（去掉内部 _t0 字段）。"""
    with _lock:
        return [{k: v for k, v in rec.items() if not k.startswith("_")}
                for rec in _records.values()]


def _now() -> str:
    """本地时间，人看的："2026-08-20 10:15:33"。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_log(rec: dict) -> None:
    """追加一行到 render_times.log：
    "2026-08-20 10:15:33 图2 嵌字 failed 总耗时32.5秒 阶段:[OCR识别2.1s, 云端翻译30.4s]"。"""
    stages = ", ".join(f"{s['stage']}{s['seconds']}s" for s in rec["stages"])
    line = (f"{rec['finished_at']} 图{rec['image_id']} {rec['kind']} "
            f"{rec['status']} 总耗时{rec['total_seconds']}秒 阶段:[{stages}]")
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # 写日志失败不影响任务本身（日志是锦上添花）