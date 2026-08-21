"""给网关的"带图请求"做体检 —— 同一张图按三种"体重"各发一次，找出 520 的病根。

为什么有它：check_key.py 发纯文字 = 200 通过；嵌字发"图+文字" = 520 失败。
差别就在"图"上：是图太大压垮了网关？还是网关的看图服务整个坏了？
光靠猜没用，这个脚本一次跑出三档数据，用数据下结论。

用法（终端里跑，路径按你的实际位置）：
    D:\\myproject\\venv\\Scripts\\python.exe check_image.py "图片路径"
建议用你上传过的那张原截图；也可以把图片文件直接拖到这个脚本上运行。

三档"体重"：
    ① 原图原样      —— 跟后端现在发的一模一样（对照，估计 520 就是它）
    ② 原尺寸压质量  —— 像素一个不少，只把 JPEG 质量压到 80，体积砍半
    ③ 长边缩到 1600 —— 像素缩水版（旧版"缩图"档位）

每档最多等 180 秒（520 一般要 100 秒左右才吐出来，等短了会误报成超时）。
最坏情况全程 9 分钟，请耐心。全程不打印 Key，只打印状态码和体积。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 控制台 GBK 防崩
except AttributeError:
    pass

import base64
import io
import time
from pathlib import Path

import httpx
from PIL import Image

# 读 .env（跟 check_key.py 同款读法；只取网址和模型名，Key 全程不打印）
env = {}
for line in Path(__file__).parent.joinpath(".env").read_text("utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    env[k.strip()] = v.strip().strip('"').strip("'")

KEY = env.get("OPENAI_API_KEY", "")
BASE = env.get("OPENAI_BASE_URL", "https://apihub.agnes-ai.cn/v1").rstrip("/")
MODEL = env.get("OPENAI_MODEL", "agnes-2.0-flash")
URL = f"{BASE}/chat/completions"

if len(sys.argv) < 2:
    print('用法：check_image.py "图片路径"（或者把图片直接拖到脚本上）')
    sys.exit(1)
src = Path(sys.argv[1])
if not src.exists():
    print(f"图片不存在：{src}")
    sys.exit(1)
if not KEY:
    print("！.env 里没找到 OPENAI_API_KEY，先回去补上再跑")
    sys.exit(1)

print(f"待测图片：{src.name}")
print(f"模型：{MODEL}   网关：{BASE}\n")


def to_data_url(buf: bytes, suffix: str) -> str:
    """二进制图片 → base64 文本。同款 vision.py 的 _to_data_url 思路。"""
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "bmp": "image/bmp"}.get(suffix.lower(), "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(buf).decode()}"


def send_one(data_url: str):
    """发一次带图请求（让模型"用一句话描述这张图"——逼它真的看图）。
    只关心 HTTP 状态码；520/超时都原样报告，不重试（体检要的是真实数据）。"""
    t0 = time.time()
    try:
        r = httpx.post(
            URL,
            headers={"Authorization": f"Bearer {KEY}"},
            json={"model": MODEL,
                  "messages": [
                      {"role": "user", "content": [
                          {"type": "text", "text": "用一句话描述这张图"},
                          {"type": "image_url", "image_url": {"url": data_url}},
                      ]},
                  ]},
            timeout=180,
        )
        return r.status_code, r.text[:100], round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001 体检脚本，什么错都如实报
        return type(e).__name__, str(e)[:100], round(time.time() - t0, 1)


# ---------------------------------------------------------------------- 三档"体重"
im = Image.open(src).convert("RGB")
w, h = im.size

# ① 原图原样：文件字节一个不动
buf1 = src.read_bytes()
# ② 原尺寸压质量：像素一个不少，JPEG 质量 80（体积砍半的常规操作）
buf2 = io.BytesIO()
im.save(buf2, "JPEG", quality=80)
# ③ 长边缩到 1600：像素缩水版
im3 = im
if max(w, h) > 1600:
    r = 1600 / max(w, h)
    im3 = im.resize((round(w * r), round(h * r)), Image.LANCZOS)
buf3 = io.BytesIO()
im3.save(buf3, "JPEG", quality=85)

tiers = [
    ("① 原图原样", to_data_url(buf1, src.suffix), len(buf1)),
    ("② 原尺寸压质量80", to_data_url(buf2.getvalue(), "jpg"), buf2.tell()),
    ("③ 长边缩到1600", to_data_url(buf3.getvalue(), "jpg"), buf3.tell()),
]

results = []
for label, data_url, nbytes in tiers:
    mb = nbytes / 1024 / 1024
    print(f"--- {label}（原图 {w}x{h}，这档 base64 后 {mb:.1f}MB）发送中…")
    code, snippet, secs = send_one(data_url)
    results.append((label, code, secs))
    print(f"    网关回复：{code}，耗时 {secs} 秒，回复前 100 字：{snippet!r}")
    if label == "① 原图原样" and code == 200:
        print("\n✅ 原图这档直接 200 了——网关现在收得下原图！")
        print("   刚才那次 520 是网关时好时坏的抽风。回 Swagger 直接重试 render 就行。")
        sys.exit(0)

# ---------------------------------------------------------------------- 下结论
print()
codes = [c for _, c, _ in results]
if any(c == 200 for c in codes):
    passed = "、".join(l for l, c, _ in results if c == 200)
    failed = "、".join(l for l, c, _ in results if c != 200)
    print(f"✅ 通过：{passed}")
    print(f"❌ 失败：{failed}")
    if "①" not in passed:
        print("结论：网关扛不住大图，图越大越容易 520。")
        print("对策：回来找我，把发送端改成\"先压质量/缩尺寸再发\"（②③档就是候选方案）。")
    else:
        print("结论：原图能通、有的档反而不通——网关时好时坏，纯抽风。")
        print("对策：回 Swagger 重试 render，多试一两次。")
else:
    print("❌ 三档全部 520——网关的看图服务整个坏了（纯文字能通、带图全不通）。")
    print("结论：这是我们代码修不了的，卖家/网关那边的锅。")
    print("对策：拿这张体检结果找卖 Key 的理论，或者等网关恢复再试。")