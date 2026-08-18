# MangaLens — 漫画 · 小说 识图翻译

上传漫画图片 / 小说文本，调用大模型完成识别与翻译，返回可下载的成品。

## 项目结构

- `frontend/` — Vue 3 + TypeScript + Element Plus 前端
- `backend/` — FastAPI + SQLite 后端

## 启动后端

```bash
D:\myproject\venv\Scripts\Activate.ps1
cd D:\py_projects_D\newcode\MangaLens\backend
python -m pip install -r requirements.txt   # 首次运行才需要
python -m uvicorn app.main:app --reload --port 8000
## 后端起来后：

API 文档（建议常看）：http://127.0.0.1:8000/docs
健康检查：http://127.0.0.1:8000/api/health
启动前端

cd D:\py_projects_D\newcode\MangaLens\frontend
npm install    # 首次运行才需要
npm run dev
浏览器访问 http://localhost:5173/