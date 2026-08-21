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
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image as PILImage

from ..config import CACHE_DIR, settings
from .prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TEXT_SYSTEM_PROMPT,
    build_render_prompt,
    build_text_prompt,
    build_translate_prompt,
)



class VisionError(RuntimeError):
    pass


class GatewayError(VisionError):
    """云端网关故障（5xx / 断连这类），报错文案已换成中文。
    它是 VisionError 的子类，但含义相反：GatewayError = "网络层的重试已经做完、
    网关还是不行"，外层的内容重试（render_translate）看到它必须直接放弃——
    否则重试叠重试，对着一个坏掉的网关干等（用户实测 520 连等 4 次）。
    """
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
    """图片转 base64 文本，塞进请求 —— 同款见 AIRoomBuilder vision.py 第50-53行。
    原图原样发送：缩图省时间但会让模型认错字/漏认气泡（用户实测），不缩。"""
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

# 单次请求超时 180 秒（3分钟）——用户拍板的最新时限，跟 main.py 的
# TASK_BUDGET_SECONDS 对齐：嵌字生死线 3分钟，一次调用就给足整段窗口，
# 让模型慢慢回话（之前 45 秒一刀切，模型慢一点就被腰斩成 ReadTimeout，
# 用户实测 id=18 连等两个 45 秒都没等到回话）
_REQUEST_TIMEOUT = 180

# 嵌字翻译的输出上限（token）：生成是耗时的大头，封顶 = 服务端生成时间封顶。
# 网关 520 的重灾区正是气泡多的重图——模型想写几千 token，服务端撑不住直接崩
# （check_image 简单输出健康 20 秒是同一证据）。3000 ≈ 三四十条气泡的量；
# 写满被掐断的半截答案由 render_translate 里的补尾兜底救回来
_RENDER_MAX_TOKENS = 3000

# 网关闸门（红绿灯）：同一时刻只放一个请求进网关。
# 后台任务是并发的——一次传好几张图 = 好几个任务同时砸网关，网关过载
# 就 520 / ReadTimeout（用户实测"任务一多网关就出问题"）。
# 排队串行后，后面的任务多等一会，但每个请求都轻装上路，不互相踩。
_gateway_lock = threading.Lock()


def _post_json(url: str, headers: dict, payload: dict, retries: int = 1) -> dict:
    """发请求并解析响应。4xx 不重试直接报错（自己的错，重试没用）。
    5xx = 网关明确报服务器故障：只重试一次，第二次还 5xx 就放弃——
    网关真挂了再试也是挂，连等 4 次又慢又难看（用户实测 520）。
    网络故障（断连 RemoteProtocolError、超时）同样只重试 1 次：网关抽风时
    连接说断就断，重试一次多半能好（用户实测 id=14）；再不行就是真不行，
    每多试一次白等超时，测试期等不起（用户拍板）。
    放弃时报 GatewayError（中文文案），不再吐 httpx 的英文长串。
    同款见 AIRoomBuilder vision.py 第98-126行。"""
    # 排队进网关：整站所有大模型调用（嵌字/书页翻译/小说txt）都从这一个
    # 闸门过，一次只放一个（见 _gateway_lock 注释），重试也占着队——
    # 重试期间别的任务不许插队加塞
    with _gateway_lock:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = httpx.post(url, headers=headers, json=payload, timeout=_REQUEST_TIMEOUT)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPStatusError, httpx.TransportError, json.JSONDecodeError) as e:
                last_err = e
                status = None
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code
                if status is not None and 400 <= status < 500:
                    raise
                # 5xx：还有重试名额就先 sleep 再试；名额用完还 5xx 就放弃。
                # 报错换成中文 + 专用类型 GatewayError——render_translate 看到它会直接放弃，
                # 不会再来一轮"内容层重试"砸同一个坏网关
                if status is not None and 500 <= status < 600 and attempt >= retries:
                    raise GatewayError(f"云端翻译网关故障（HTTP {status}），稍后再试") from e
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 8))  # 1s, 2s, 4s 退避重试
                    continue
                # 连接异常 / 响应不是合法 JSON：重试次数用完还是不行，同样换中文报错
                raise GatewayError(f"云端翻译网关连接异常（{type(e).__name__}），稍后再试") from e
    assert last_err is not None
    raise last_err


def _call_openai(path: Path, style: str) -> str:
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
                    {"type": "text", "text": build_translate_prompt(style)},
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


def _call_mock(path: Path, style: str = "直译") -> str:
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

    raw = _PROVIDERS[provider](path, style)
    data = extract_json(raw)
    data.setdefault("status", "done")

    if settings.vision_cache_enabled:
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    return data
# --------------------------------------------------------------------------- 纯文本翻译

def translate_text(text: str, style: str = "文学风") -> str:
    """翻译一段纯文本（无图）。
    跟 analyze_image 的区别：
    1. 请求里没有 image_url，只有文字
    2. 返回纯译文，不解析 JSON
    3. v1 不做缓存——整本小说切成几十块，缓存命中率低，先不背这个复杂度
    """
    provider = settings.resolved_provider()
    if provider == "mock":
        # mock 兜底：不联网验证链路用。整段原样返回，一眼就能认出来。
        return f"【mock译文】{text[:40]}"

    data = _post_json(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        payload={
            "model": settings.openai_model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": TEXT_SYSTEM_PROMPT},
                {"role": "user", "content": build_text_prompt(style, text)},
            ],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def render_translate(path: str | Path, items: list[dict],
                     style: str = "口语风") -> list[dict]:
    """嵌字管线专用：视觉模型独立看原图翻译（第一版定稿方案，用户拍板回归）。
    模型一个气泡一条，报 original（逐字照抄，本地配对用）+ translation；
    位置是本地工作：main.py 用 pair_entries 把 original 配回 OCR 片段框，
    模型完全不掺和定位。
    mock 自检：每条抄回原位（确定性身份映射）——成品图应跟原图几乎一样，
    哪里不一样 = 哪里几何有毛病。
    缓存：同一张图 + 同一 prompt 版本不重复调模型；prompt 改了要升级
    prompts.py 的 PROMPT_VERSION，缓存自动失效。
    想强制重新翻译：.env 里 VISION_CACHE_ENABLED=false。"""
    path = Path(path)
    provider = settings.resolved_provider()
    if provider == "mock":
        return [{"original": it["text"], "translation": it["text"]}
                for it in items]

    cache_key = hashlib.sha256(
        f"{_file_sha256(path)}|{PROMPT_VERSION}|{style}".encode()
    ).hexdigest()[:32]
    cache_file = CACHE_DIR / f"render_{cache_key}.json"
    if settings.vision_cache_enabled and cache_file.exists():
        return json.loads(cache_file.read_text("utf-8"))

    # 一次机会、不重试：3分钟生死线里，180 秒窗口整段给这一次调用——
    # 重试一次 = 再来 180 秒 = 6 分钟，直接越过嵌字任务的时间预算
    data = _post_json(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        retries=0,
        payload={
            "model": settings.openai_model,
            "temperature": 0.1,
            # 输出封顶（见 _RENDER_MAX_TOKENS 注释）：重图写不满就掐断，
            # 半截答案在下面补尾救回来，翻完的条目照用
            "max_tokens": _RENDER_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": build_render_prompt(style)},
                    {"type": "image_url",
                     "image_url": {"url": _to_data_url(path)}},
                ]},
            ],
        },
    )
    content = data["choices"][0]["message"]["content"]
    truncated = data["choices"][0].get("finish_reason") == "length"
    if not truncated:
        parsed = extract_json(content)
    else:
        # 写满上限被网关掐断，半截 JSON 差个结尾。兜底①：先当它恰好断在
        # 两条之间——清逗号补 ]} 直接解析；兜底②：还不行就是最后一条
        # 写到一半，把写坏的丢掉再补。翻完的照用，没写到的本地配对
        # 认领不上 → 只擦不画（用户拍板"至少要出图"）
        try:
            parsed = extract_json(content.rstrip().rstrip(",") + "]}")
        except VisionError:
            cut_at = content.rfind('"original"')
            if cut_at == -1:
                raise
            parsed = extract_json(content[:cut_at].rstrip().rstrip(",") + "]}")
    raw_texts = parsed.get("texts") if isinstance(parsed, dict) else None
    entries = []
    for t in raw_texts if isinstance(raw_texts, list) else []:
        if not isinstance(t, dict):
            continue
        og = t.get("original")
        tr = t.get("translation")
        if not isinstance(og, str) or not og.strip():
            continue
        if not isinstance(tr, str) or not tr.strip():
            continue
        entries.append({"original": og.strip(), "translation": tr.strip()})
    if not entries:
        raise VisionError("模型没有返回翻译条目，重新发起一次")
    # 截断的答卷不进缓存（沿用老规矩：只有完整答卷才值得缓存）——
    # 半截结果缓存了，同图下次重测会一直拿残卷
    if settings.vision_cache_enabled and not truncated:
        cache_file.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), "utf-8")
    return entries
