"""多模态视觉模型适配层 —— 同款见 AIRoomBuilder/backend/app/services/vision.py。

提供统一入口 analyze_image(path) -> dict：
- mock provider：没有 Key 也能跑通，用内置样例数据
- openai provider：真调 agnes 大模型识别+翻译
- 结果缓存：同一张图不重复烧钱，开发期反复调试不浪费额度
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import CACHE_DIR, settings
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_translate_prompt


class VisionError(RuntimeError):
    pass


# --------------------------------------------------------------------------- 工具函数

def _file_sha256(path: Path) -> str:
    """计算文件哈希，用作缓存键 —— 同款见 AIRoomBuilder vision.py 第42-47行"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_data_url(path: Path) -> str:
    """图片转 base64 文本，塞进请求 —— 同款见 AIRoomBuilder vision.py 第50-53行"""
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def extract_json(text: str) -> dict[str, Any]:
    """从模型返回的自由文本里抠出第一个完整 JSON —— 同款见 AIRoomBuilder vision.py 第56-88行。
    模型经常裹 ```json 或在前后加废话，必须容错。"""
    if not text:
        raise VisionError("模型返回为空")

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)

    start = text.find("{")
    if start == -1:
        raise VisionError(f"返回内容中找不到 JSON: {text[:200]}")

    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise VisionError("JSON 括号未闭合")


# --------------------------------------------------------------------------- 调用大模型

_REQUEST_TIMEOUT = 300  # 视觉模型较慢，放宽到 5 分钟 —— 同款 vision.py 第95行


def _post_json(url: str, headers: dict, payload: dict, retries: int = 3) -> dict:
    """发请求并解析响应。5xx/超时自动重试；4xx 不重试直接报错。
    同款见 AIRoomBuilder vision.py 第98-126行。"""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=_REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPStatusError, httpx.TimeoutException, json.JSONDecodeError) as e:
            last_err = e
            status = None
            if isinstance(e, httpx.HTTPStatusError):
                status = e.response.status_code
            if status is not None and 400 <= status < 500:
                raise
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))  # 1s, 2s, 4s 退避重试
                continue
            raise
    assert last_err is not None
    raise last_err


def _call_openai(path: Path) -> str:
    """调 agnes 网关 —— 同款见 AIRoomBuilder vision.py 第129-146行。
    你之前 401 报错的那段代码就是它的同款。"""
    data = _post_json(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        payload={
            "model": settings.openai_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": build_translate_prompt()},
                    {"type": "image_url", "image_url": {"url": _to_data_url(path)}},
                ]},
            ],
        },
    )
    return data["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------- mock 兜底

MOCK_RESULT: dict[str, Any] = {
    "status": "done",
    "texts": [
        {"original": "おはよう、今日もいい天気だね", "translation": "早上好，今天天气真不错"},
        {"original": "ああ、本当だな", "translation": "是啊，真的呢"},
        {"original": "ドキドキ...", "translation": "心跳加速……"},
    ],
}


def _call_mock(path: Path) -> str:
    """离线样例：不联网也能验证整条链路 —— 同款见 AIRoomBuilder vision.py 第261-265行"""
    return json.dumps(MOCK_RESULT, ensure_ascii=False)


_PROVIDERS = {
    "mock": _call_mock,
    "openai": _call_openai,
}


# --------------------------------------------------------------------------- 统一入口

def analyze_image(path: str | Path, style: str = "直译", force: bool = False) -> dict[str, Any]:
    """对一张图片做识别+翻译。带缓存：同一张图+同一prompt版本不重复调模型。
    同款见 AIRoomBuilder vision.py 第278-324行。"""
    path = Path(path)
    if not path.exists():
        raise VisionError(f"图片不存在: {path}")

    provider = settings.resolved_provider()
    cache_key = hashlib.sha256(
        f"{_file_sha256(path)}|{PROMPT_VERSION}|{provider}|{style}".encode()
    ).hexdigest()[:32]
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if settings.vision_cache_enabled and cache_file.exists() and not force:
        return json.loads(cache_file.read_text("utf-8"))

    raw = _PROVIDERS[provider](path)
    data = extract_json(raw)
    data.setdefault("status", "done")

    if settings.vision_cache_enabled:
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    return data
