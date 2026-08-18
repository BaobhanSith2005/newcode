"""翻译 Prompt。

设计原则（改 Prompt 前务必先读）—— 同款见 AIRoomBuilder/backend/app/services/prompts.py 第1-14行：
1. **风格受控词表。** 翻译风格从固定的几种里选，不让模型自由发挥，
   否则同一个风格要求会写出千奇百怪的译文。
2. **严格 JSON 输出。** 模型偶尔会裹 ```json 或加废话，代码侧必须容错解析。
3. **改本文件必须升级 PROMPT_VERSION，否则命中旧缓存。**
"""
from __future__ import annotations

PROMPT_VERSION = "p1"

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
