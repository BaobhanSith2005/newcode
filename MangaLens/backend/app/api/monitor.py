"""计时台账接口 —— 测试阶段监控用。

同款结构见 api/batches.py：一个 APIRouter"插座"，main.py 里 include_router。
打开 http://127.0.0.1:8000/docs 就能看到 GET /api/monitor，点 Execute 看台账。
"""
from fastapi import APIRouter

from ..services.timing import list_records

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("", summary="监控：后台任务计时台账（测试阶段用）")
def get_monitor():
    """返回每个后台任务最新一次运行的计时：
    - status: running / done / failed（任务跑着的时候点 Execute，能看阶段秒数实时涨）
    - stages: 每个阶段的累计秒数（OCR 识别、云端翻译、LaMa 擦除、画字保存）
    - total_seconds: 总耗时
    内存台账重启后端会清空；历史看 backend/data/render_times.log（每跑完一次追加一行）。"""
    return {"records": list_records()}