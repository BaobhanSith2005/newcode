# AI Room Builder

基于多模态大模型的**室内空间理解与 Web 三维场景生成平台**。

上传一张房间照片 → 视觉模型理解空间布局 → 生成结构化场景数据 → 浏览器中渲染可交互的 3D 房间。

---

## 核心设计

不做真实三维重建，而是走「**视觉理解 → 结构推理 → 确定性渲染**」路线：

```
照片 ──VLM──→ analysis.json ──查表+求解──→ scene.json ──Three.js──→ 3D 场景
       ↑                        ↑
   唯一的不确定环节          全部为确定性代码
```

AI 只负责「看懂图里有什么、大致在哪」，**尺寸、布局、碰撞、朝向全部由确定性代码接管**。
这样即使模型输出抖动，最终场景也始终是合法的。

三条关键约束（详见 `docs/00-方案评审与修正.md`）：

1. **不问图像坐标，只问俯视平面坐标** —— 图像坐标转平面坐标需要相机位姿和深度，那才是真三维重建
2. **不问米制尺寸，只问 S/M/L** —— 尺寸查家具先验表，比问模型准且可复现
3. **必有降级渲染** —— 缺 glb 时用参数化几何体，保证任何分析结果都能出图

---

## 快速开始

### 后端

```bash
cd backend
python -m venv ../venv                      # 已有 venv 可跳过
../venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env                        # 不填 Key 也能跑（自动使用 mock）
../venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173

### 冒烟测试

不启动服务，直接验证「分析 → 布局求解 → scene.json」全链路及三项布局不变量：

```bash
cd backend && ../venv/Scripts/python smoke_test.py
```

---

## 接入真实视觉模型

编辑 `backend/.env`：

```ini
VISION_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxx
```

支持 `mock` / `dashscope`(Qwen-VL) / `openai`(GPT-4o) / `gemini`。
**未配置对应 Key 时自动回退到 mock**，不会报错。

> 开发期建议保持 `VISION_CACHE_ENABLED=true`：相同图片 + 相同 Prompt 版本会命中缓存，
> 既省钱，又保证调试布局算法时结果可复现。

---

## 目录结构

```
AIRoomBuilder
├── docs/
│   ├── 00-方案评审与修正.md      技术选型评审、踩坑点分析
│   ├── 01-scene协议.md           ★ AI 与渲染器之间的数据契约
│   ├── 02-开发路线.md            任务拆分与 AI 协作提示词
│   └── scene.schema.json         JSON Schema 校验文件
│
├── backend/
│   ├── app/
│   │   ├── api/                  projects / images / scenes 三组接口
│   │   ├── services/
│   │   │   ├── prompts.py        ★ 视觉模型 Prompt
│   │   │   ├── vision.py         模型适配层 + 结果缓存
│   │   │   ├── catalog.py        ★ 家具尺寸先验表
│   │   │   └── scene_builder.py  ★ 布局求解器
│   │   ├── models.py             Project / Image / Scene
│   │   └── main.py
│   └── smoke_test.py             全链路 + 布局不变量测试
│
├── frontend/src/
│   ├── three/
│   │   ├── RoomRenderer.ts       ★ scene.json → Three.js 场景
│   │   └── primitives.ts         参数化替身几何体
│   ├── components/SceneCanvas.vue
│   ├── stores/workspace.ts
│   └── types/scene.ts            与 scene.schema.json 同步
│
└── models/                       家具 glb 资产（见目录内 README）
```

★ 标记的是修改前需要先读文档的核心文件。

---

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Element Plus |
| 3D | Three.js + glTF |
| 后端 | Python 3.10 + FastAPI + SQLAlchemy + SQLite |
| AI | Qwen-VL / GPT-4o / Gemini / agnes-2.0-flash（可切换，含离线 mock） |

PostgreSQL / Redis / Celery / Docker 等重型组件在有明确需求时再引入，
触发条件见 `docs/02-开发路线.md` 末节。
