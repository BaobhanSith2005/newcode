"""直连网关给 Key 做体检 —— 绕开 MangaLens 全部代码，一步定生死。

为什么有这个脚本：后端报 401（网关不认 Key），要分清是
① Key 本身有问题（找卖 Key 的人）还是 ② 我们后端哪里读错了（回来找我）。

用法（终端里跑，路径按你的实际位置）：
    D:\\myproject\\venv\\Scripts\\python.exe check_key.py

全程只打印 Key 的"指纹"（首尾几位 + 长度），完整 Key 绝不输出——贴给别人看也安全。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 控制台 GBK 防崩
except AttributeError:
    pass

from pathlib import Path

import httpx

# 从 backend/.env 里读 Key（跟 config.py 同一个文件、同一种读法）
env = {}
for line in Path(__file__).parent.joinpath(".env").read_text("utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    env[k.strip()] = v.strip().strip('"').strip("'")

key = env.get("OPENAI_API_KEY", "")
print(f"读到 Key：共 {len(key)} 字符，开头 {key[:6]}，结尾 {key[-4:]}")
if not key:
    print("！.env 里没找到 OPENAI_API_KEY，后端读到的也是空——这就是病根")
    sys.exit(1)

# 发一个最小的翻译请求（内容就一个字"说1"），只关心 HTTP 状态码
try:
    r = httpx.post(
        "https://apihub.agnes-ai.cn/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "agnes-2.0-flash",
              "messages": [{"role": "user", "content": "说1"}]},
        timeout=60,
    )
    print(f"网关 HTTP 状态码：{r.status_code}")
    if r.status_code == 200:
        print("✅ Key 有效、网关正常——如果之前报 401，是当时 .env 里的 Key 不被网关认（换回好 Key 即可），不是后端读错")
    else:
        print("网关的回复（截断300字符）：", r.text[:300])
        if r.status_code in (401, 403):
            print("❌ 网关不认这个 Key——去找卖 Key 的：没激活 / 没充值 / 发错 Key")
except Exception as e:
    print("❌ 连不上网关：", type(e).__name__, e)
