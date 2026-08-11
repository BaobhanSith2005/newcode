"""多模态视觉模型适配层。

提供统一入口 `analyze_image(path) -> dict`，屏蔽不同厂商的 API 差异。

三个工程化要点：
1. **mock provider**：没有任何 API Key 也能跑通全链路，方便先把渲染和布局算法调好。
2. **结果缓存**：key = sha256(图片) + prompt_version + provider。开发期反复调 Prompt
   不会重复烧钱，而且结果可复现——否则你没法判断布局算法的改动到底有没有生效。
3. **鲁棒的 JSON 解析**：模型经常裹一层 ```json 或在前后加废话，必须容错。
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
from .color_service import enrich_objects_with_color
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt


class VisionError(RuntimeError):
    pass


class EmptyResponseError(VisionError):
    """模型返回 200 但 content 为空。多为网关侧瞬时抖动（带 reasoning 的模型尤甚），
    应作为可重试故障处理，而非直接判失败。"""
    pass


# --------------------------------------------------------------------------- 工具

def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def extract_json(text: str) -> dict[str, Any]:
    """从模型返回的自由文本里抠出第一个完整 JSON 对象。"""
    if not text:
        raise EmptyResponseError("模型返回为空")

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


# --------------------------------------------------------------------------- providers

# 视觉模型（尤其带图像的请求）可能较慢，网关偶发 504/超时。
# 这里把超时放宽到 5 分钟，并对 5xx / 超时做有限重试。
_REQUEST_TIMEOUT = 300


def _post_json(url: str, headers: dict, payload: dict, retries: int = 3) -> dict:
    """发送请求并把响应解析成 dict。对以下瞬时故障自动重试：

    - 服务端错误 5xx（网关偶发 502/504）
    - 超时（图像请求通常较慢）
    - 响应体非合法 JSON（网关偶发返回空 body / HTML 错误页）

    4xx（请求本身的问题）不重试，直接报错。
    """
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
            # 仅对服务端错误(5xx)重试；4xx 通常是请求本身的问题，不重试
            if status is not None and 400 <= status < 500:
                raise
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))  # 1s, 2s, 4s 退避
                continue
            raise
    assert last_err is not None
    raise last_err


def _call_openai(path: Path) -> str:
    data = _post_json(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        payload={
            "model": settings.openai_model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": build_user_prompt()},
                    {"type": "image_url", "image_url": {"url": _to_data_url(path)}},
                ]},
            ],
        },
    )
    return data["choices"][0]["message"]["content"]


def _call_dashscope(path: Path) -> str:
    """阿里云百炼 Qwen-VL，走 OpenAI 兼容端点。国内网络最省心的选择。"""
    data = _post_json(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
        payload={
            "model": settings.dashscope_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": _to_data_url(path)}},
                    {"type": "text", "text": build_user_prompt()},
                ]},
            ],
        },
    )
    return data["choices"][0]["message"]["content"]


def _call_gemini(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}",
        headers={"Content-Type": "application/json"},
        payload={
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [
                {"text": build_user_prompt()},
                {"inline_data": {"mime_type": mime,
                                 "data": base64.b64encode(path.read_bytes()).decode()}},
            ]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        },
    )
    return data["candidates"][0]["content"]["parts"][0]["text"]


MOCK_SAMPLES: dict[str, dict[str, Any]] = {
    "living_room": {
        "room_type": "living_room",
        "style": "modern",
        "dominant_colors": ["#efe9df", "#8d9aaf"],
        "objects": [
            {"category": "sofa", "label": "三人布艺沙发", "floor_uv": [0.32, 0.16],
             "against_wall": "north", "rotation_hint": "south", "size_class": "L",
             "bbox": [0, 0, 0, 0], "color": "#8d9aaf", "confidence": 0.93},
            {"category": "coffee_table", "label": "木质茶几", "floor_uv": [0.34, 0.42],
             "against_wall": "center", "rotation_hint": "south", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#a9855f", "confidence": 0.88},
            {"category": "tv_stand", "label": "电视柜", "floor_uv": [0.34, 0.9],
             "against_wall": "south", "rotation_hint": "north", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#6f665c", "confidence": 0.85},
            {"category": "tv", "label": "壁挂电视", "floor_uv": [0.34, 0.97],
             "against_wall": "south", "rotation_hint": "north", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#26282b", "confidence": 0.9},
            {"category": "rug", "label": "米色地毯", "floor_uv": [0.34, 0.45],
             "against_wall": "center", "rotation_hint": "north", "size_class": "L",
             "bbox": [0, 0, 0, 0], "color": "#c9bda6", "confidence": 0.7},
            {"category": "bookshelf", "label": "开放书架", "floor_uv": [0.9, 0.35],
             "against_wall": "east", "rotation_hint": "west", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#8a7355", "confidence": 0.76},
            {"category": "plant", "label": "散尾葵", "floor_uv": [0.08, 0.12],
             "against_wall": "center", "rotation_hint": "south", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#5c7f52", "confidence": 0.8},
            {"category": "floor_lamp", "label": "落地灯", "floor_uv": [0.06, 0.72],
             "against_wall": "center", "rotation_hint": "east", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#d8cfa8", "confidence": 0.72},
            {"category": "ceiling_lamp", "label": "吸顶灯", "floor_uv": [0.5, 0.5],
             "against_wall": "center", "rotation_hint": "south", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#efe6c8", "confidence": 0.65},
        ],
        "openings": [
            {"type": "window", "wall": "west", "offset": 0.45, "size_class": "L"},
            {"type": "door", "wall": "south", "offset": 0.85, "size_class": "M"},
        ],
        "notes": "[MOCK] 现代风格客厅样例数据",
    },
    "bedroom": {
        "room_type": "bedroom",
        "style": "nordic",
        "dominant_colors": ["#f2ece2", "#c9c2b6"],
        "objects": [
            {"category": "bed", "label": "双人床", "floor_uv": [0.5, 0.3],
             "against_wall": "north", "rotation_hint": "south", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#c9c2b6", "confidence": 0.95},
            {"category": "nightstand", "label": "左床头柜", "floor_uv": [0.2, 0.14],
             "against_wall": "north", "rotation_hint": "south", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#a08a6a", "confidence": 0.83},
            {"category": "nightstand", "label": "右床头柜", "floor_uv": [0.8, 0.14],
             "against_wall": "north", "rotation_hint": "south", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#a08a6a", "confidence": 0.81},
            {"category": "wardrobe", "label": "推拉门衣柜", "floor_uv": [0.12, 0.65],
             "against_wall": "west", "rotation_hint": "east", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#8f7f6b", "confidence": 0.87},
            {"category": "desk", "label": "书桌", "floor_uv": [0.85, 0.7],
             "against_wall": "east", "rotation_hint": "west", "size_class": "S",
             "bbox": [0, 0, 0, 0], "color": "#a58c6f", "confidence": 0.74},
            {"category": "office_chair", "label": "办公椅", "floor_uv": [0.7, 0.7],
             "against_wall": "center", "rotation_hint": "east", "size_class": "M",
             "bbox": [0, 0, 0, 0], "color": "#4a4f57", "confidence": 0.7},
            {"category": "curtain", "label": "窗帘", "floor_uv": [0.5, 0.98],
             "against_wall": "south", "rotation_hint": "north", "size_class": "L",
             "bbox": [0, 0, 0, 0], "color": "#ded5c6", "confidence": 0.6},
        ],
        "openings": [{"type": "window", "wall": "south", "offset": 0.5, "size_class": "L"}],
        "notes": "[MOCK] 北欧风卧室样例数据",
    },
}


def _call_mock(path: Path) -> str:
    """离线样例。按图片哈希在两套布局间切换，方便观察不同分析结果的渲染差异。"""
    keys = sorted(MOCK_SAMPLES)
    variant = int(_file_sha256(path)[:8], 16) % len(keys)
    return json.dumps(MOCK_SAMPLES[keys[variant]], ensure_ascii=False)


_PROVIDERS = {
    "mock": _call_mock,
    "openai": _call_openai,
    "dashscope": _call_dashscope,
    "gemini": _call_gemini,
}


# --------------------------------------------------------------------------- 入口

def analyze_image(path: str | Path, force: bool = False) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise VisionError(f"图片不存在: {path}")

    provider = settings.resolved_provider()
    cache_key = hashlib.sha256(
        f"{_file_sha256(path)}|{PROMPT_VERSION}|{provider}".encode()
    ).hexdigest()[:32]
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if settings.vision_cache_enabled and cache_file.exists() and not force:
        data = json.loads(cache_file.read_text("utf-8"))
        data.setdefault("_meta", {})["cached"] = True
        return data

    # 模型偶发返回空 content（网关侧抖动，HTTP 仍为 200）。把它当作瞬时故障重试，
    # 避免一次空回包就判整张图失败。最多重试 4 次，退避 1s/2s。
    raw: str | None = None
    for attempt in range(5):
        try:
            raw = _PROVIDERS[provider](path)
            data = extract_json(raw)
            break
        except EmptyResponseError:
            if attempt < 4:
                time.sleep(min(2 ** attempt, 4))
                continue
            raise

    # 对真实视觉模型补充 OpenCV 颜色分析（mock 使用预设颜色，避免编造 bbox 落在随机图片上）
    if provider != "mock" and path.exists():
        try:
            data["objects"] = enrich_objects_with_color(path, data.get("objects") or [])
        except Exception as exc:  # noqa: BLE001 颜色失败不应导致整图分析失败
            data.setdefault("_warnings", []).append(f"color_analysis_failed: {exc}")

    data["_meta"] = {
        "provider": provider,
        "prompt_version": PROMPT_VERSION,
        "cached": False,
    }

    if settings.vision_cache_enabled:
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    return data
