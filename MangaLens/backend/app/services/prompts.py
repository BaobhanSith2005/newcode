"""翻译 Prompt。

设计原则（改 Prompt 前务必先读）—— 同款见 AIRoomBuilder/backend/app/services/prompts.py 第1-14行：
1. **风格受控词表。** 翻译风格从固定的几种里选，不让模型自由发挥，
   否则同一个风格要求会写出千奇百怪的译文。
2. **严格 JSON 输出。** 模型偶尔会裹 ```json 或加废话，代码侧必须容错解析。
3. **改本文件必须升级 PROMPT_VERSION，否则命中旧缓存**（build_render_prompt 的嵌字翻译同样走这条缓存）。
"""
from __future__ import annotations

PROMPT_VERSION = "p6"

# 角色设定 —— 同款见 AIRoomBuilder prompts.py 第27-28行 SYSTEM_PROMPT
SYSTEM_PROMPT = """你是一名资深漫画/轻小说本地化译者，擅长把外语内容翻译成自然流畅的中文。
你只输出 JSON，不输出任何解释、注释或 Markdown 代码块标记。"""

# 风格受控词表 —— 同款见 AIRoomBuilder prompts.py 第22-25行 ROOM_TYPES
# 前端下拉框可选的风格，必须跟这里一致
TRANSLATION_STYLES = {
    "直译": "忠实原文，逐句对应，不增删内容，不加修饰",
    "文学风": "译文优美流畅，像出版级轻小说的文笔，保留意境与修辞",
    "口语风": "像朋友聊天一样自然，用词活泼，可适度使用流行语",
    "古风": "使用典雅的中文，如武侠小说口吻，但保持可读性",
}


def build_translate_prompt(style: str = "直译") -> str:
    """拼出给大模型的用户指令 —— 同款见 AIRoomBuilder prompts.py 第31行 build_user_prompt。
    风格要求从词表取；词表里没有的就用直译，避免把前端乱传的值塞给模型。"""
    style_rule = TRANSLATION_STYLES.get(style, TRANSLATION_STYLES["直译"])
    return f"""识别这张图片中的所有文字，翻译成中文。

## 翻译风格要求
{style_rule}

## 翻译规则
1. 按阅读顺序输出文字（漫画从上到下、从右到左）
2. 人名、地名保持原文音译，全篇统一
3. 拟声词（如"ドキドキ"）译成中文常用拟声表达
4. 只翻译图片中实际存在的文字，不要凭空补充

## 输出格式（严格 JSON，不要加代码块）

{{
  "texts": [
    {{"original": "图片中的原文", "translation": "翻译后的中文"}}
  ]
}}"""

# 小说文本翻译的角色设定（纯文本，不带图）
TEXT_SYSTEM_PROMPT = """你是一名资深中文小说译者，擅长把外文小说翻译成出版级流畅中文。
你只输出译文本身，不输出任何解释、注释或 Markdown 代码块标记。"""


def build_text_prompt(style: str, text: str) -> str:
    """拼出小说文本翻译指令。
    跟 build_translate_prompt 的三个区别：
    1. 不带图：纯文字翻译，大模型只看文字
    2. 不要 JSON：直接输出译文段落（图片版要 JSON 是因为要拆"原文-译文"对照）
    3. 风格默认文学风：小说翻译的自然选择，不是漫画版的"直译"默认
    """
    style_rule = TRANSLATION_STYLES.get(style, TRANSLATION_STYLES["直译"])
    return f"""把下面的小说文本翻译成中文。

## 翻译风格要求
{style_rule}

## 翻译规则
1. 保持段落结构：有几段就输出几段译文，段与段之间用空行分隔
2. 人名、地名用中文通用译法，同一人名前后必须一致
3. 只输出译文，不要原文对照、不要解释、不要代码块

## 待翻译文本

{text}"""

# 漫画嵌字的翻译指令（带图，口语风固定）—— 第一版定稿方案（用户拍板回归）
def build_render_prompt(style: str = "口语风") -> str:
    """拼出嵌字管线的翻译指令。
    模型独立看原图：一个气泡一条，报 original（逐字照抄，本地配对用）
    + translation。位置配对是本地工作（difflib 配 OCR 坐标），模型不掺和。
    p6 精简版（用户拍板）：砍掉自查和阅读顺序这类"漂亮话"，只留管线
    机械上必须的 4 条硬规则——指令越短模型出话越快，网关 520 频发期
    争取在服务端抽风前回话。
    （改这里必须升级 PROMPT_VERSION——嵌字缓存吃它）"""
    style_rule = TRANSLATION_STYLES.get(style, TRANSLATION_STYLES["口语风"])
    return f"""识别这张漫画图片里的气泡台词，逐条翻译成中文。{style_rule}

规则（都是硬要求）：
1. 一个气泡一条；气泡内多行台词连起来译，别拆多条
2. "original" 逐字照抄图片原文，一字不差（本地靠它配位置）
3. 译文换行数跟原文行数一致，换行写 \\n，每行别太长
4. 双引号写成 \\"（转义）；非台词的文字（页码、水印）不输出

输出格式（严格 JSON，不要代码块）：
{{"texts": [{{"original": "图片原文", "translation": "中文译文"}}]}}"""
