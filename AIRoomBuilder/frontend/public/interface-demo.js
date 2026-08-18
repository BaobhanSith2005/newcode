/* ============================================================
 * AI Room Builder 后端接口对接 Demo —— 纯原生 JavaScript
 * - 使用 XMLHttpRequest（ajax），不依赖 jQuery
 * - 面向过程写法：每个接口都是独立的全局函数，不封装类 / 通用请求层
 * - 覆盖后端全部接口，并在末尾提供「一键跑通流程」串联示例
 * ============================================================ */

/* 读取页面上的「API 基础地址」（默认 /api，经 Vite 代理到 :8000） */
function readBase() {
  var v = document.getElementById('apiBase').value.trim();
  return v || '/api';
}

/* 把返回内容格式化显示到页面（纯展示辅助，不涉及接口封装） */
function showResult(title, raw) {
  var box = document.getElementById('result');
  var text = raw;
  try {
    text = JSON.stringify(JSON.parse(raw), null, 2);
  } catch (e) {
    /* 不是 JSON 就原样显示 */
  }
  box.textContent = '【' + title + '】\n' + text;
}

/* 统一的网络错误提示 */
function netError(title, xhr) {
  showResult(title + ' 网络错误', (xhr.responseText || '无法连接后端，请确认后端已启动且 CORS 已放行'));
}

/* ----------------------------------------------------------
 * 1. GET /api/health —— 健康检查
 * -------------------------------------------------------- */
function apiHealth() {
  var base = readBase();
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/health');
  xhr.onload = function () {
    showResult('GET /api/health (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/health', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 2. POST /api/projects —— 创建项目
 *    请求体 JSON：{ "name": "项目名称" }
 * -------------------------------------------------------- */
function apiCreateProject() {
  var base = readBase();
  var name = document.getElementById('projectName').value || '未命名项目';
  var xhr = new XMLHttpRequest();
  xhr.open('POST', base + '/projects');
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onload = function () {
    showResult('POST /api/projects (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('POST /api/projects', xhr); };
  xhr.send(JSON.stringify({ name: name }));
}

/* ----------------------------------------------------------
 * 3. GET /api/projects —— 项目列表
 * -------------------------------------------------------- */
function apiListProjects() {
  var base = readBase();
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/projects');
  xhr.onload = function () {
    showResult('GET /api/projects (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/projects', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 4. GET /api/projects/{id} —— 获取单个项目
 * -------------------------------------------------------- */
function apiGetProject() {
  var base = readBase();
  var pid = document.getElementById('projectId').value;
  if (!pid) { alert('请填写 projectId'); return; }
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/projects/' + pid);
  xhr.onload = function () {
    showResult('GET /api/projects/' + pid + ' (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/projects/{id}', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 5. DELETE /api/projects/{id} —— 删除项目（级联删图片与场景）
 * -------------------------------------------------------- */
function apiDeleteProject() {
  var base = readBase();
  var pid = document.getElementById('projectId').value;
  if (!pid) { alert('请填写 projectId'); return; }
  if (!confirm('确认删除项目 ' + pid + ' 及其下所有图片/场景？')) return;
  var xhr = new XMLHttpRequest();
  xhr.open('DELETE', base + '/projects/' + pid);
  xhr.onload = function () {
    showResult('DELETE /api/projects/' + pid + ' (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('DELETE /api/projects/{id}', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 6. POST /api/images/upload?project_id=xxx —— 上传房间照片
 *    表单 multipart：字段名 file；project_id 走 query 参数
 * -------------------------------------------------------- */
function apiUploadImage() {
  var base = readBase();
  var pid = document.getElementById('projectId').value;
  var fileInput = document.getElementById('imageFile');
  if (!pid) { alert('请填写 projectId'); return; }
  if (!fileInput.files.length) { alert('请选择一张图片文件'); return; }

  var fd = new FormData();
  fd.append('file', fileInput.files[0]);

  var xhr = new XMLHttpRequest();
  xhr.open('POST', base + '/images/upload?project_id=' + encodeURIComponent(pid));
  xhr.onload = function () {
    showResult('POST /api/images/upload (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('POST /api/images/upload', xhr); };
  xhr.send(fd);
}

/* ----------------------------------------------------------
 * 7. GET /api/images?project_id=xxx —— 图片列表
 * -------------------------------------------------------- */
function apiListImages() {
  var base = readBase();
  var pid = document.getElementById('projectId').value;
  if (!pid) { alert('请填写 projectId'); return; }
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/images?project_id=' + encodeURIComponent(pid));
  xhr.onload = function () {
    showResult('GET /api/images (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/images', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 8. GET /api/images/{id}/analysis —— 轮询分析结果
 *    轮询直到 status=done；失败看 error 字段
 * -------------------------------------------------------- */
function apiGetAnalysis() {
  var base = readBase();
  var iid = document.getElementById('imageId').value;
  if (!iid) { alert('请填写 imageId'); return; }
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/images/' + iid + '/analysis');
  xhr.onload = function () {
    showResult('GET /api/images/' + iid + '/analysis (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/images/{id}/analysis', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 9. POST /api/images/{id}/reanalyze —— 重新分析
 * -------------------------------------------------------- */
function apiReanalyze() {
  var base = readBase();
  var iid = document.getElementById('imageId').value;
  if (!iid) { alert('请填写 imageId'); return; }
  var xhr = new XMLHttpRequest();
  xhr.open('POST', base + '/images/' + iid + '/reanalyze');
  xhr.onload = function () {
    showResult('POST /api/images/' + iid + '/reanalyze (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('POST /api/images/{id}/reanalyze', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 10. POST /api/scenes/generate —— 生成 scene.json
 *     请求体 JSON：{ "image_id": 1, "room": { "width": 5 } }（room 可选）
 * -------------------------------------------------------- */
function apiGenerateScene() {
  var base = readBase();
  var iid = document.getElementById('imageId').value;
  if (!iid) { alert('请填写 imageId'); return; }

  var room = {};
  var w = document.getElementById('roomW').value;
  var d = document.getElementById('roomD').value;
  var h = document.getElementById('roomH').value;
  if (w) room.width = parseFloat(w);
  if (d) room.depth = parseFloat(d);
  if (h) room.height = parseFloat(h);

  var body = { image_id: parseInt(iid, 10) };
  if (Object.keys(room).length > 0) body.room = room;

  var xhr = new XMLHttpRequest();
  xhr.open('POST', base + '/scenes/generate');
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onload = function () {
    showResult('POST /api/scenes/generate (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('POST /api/scenes/generate', xhr); };
  xhr.send(JSON.stringify(body));
}

/* ----------------------------------------------------------
 * 11. GET /api/scenes?project_id=xxx —— 场景列表
 * -------------------------------------------------------- */
function apiListScenes() {
  var base = readBase();
  var pid = document.getElementById('projectId').value;
  if (!pid) { alert('请填写 projectId'); return; }
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/scenes?project_id=' + encodeURIComponent(pid));
  xhr.onload = function () {
    showResult('GET /api/scenes (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/scenes', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 12. GET /api/scenes/{id} —— 获取单个场景
 * -------------------------------------------------------- */
function apiGetScene() {
  var base = readBase();
  var sid = document.getElementById('sceneId').value;
  if (!sid) { alert('请填写 sceneId'); return; }
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/scenes/' + sid);
  xhr.onload = function () {
    showResult('GET /api/scenes/' + sid + ' (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/scenes/{id}', xhr); };
  xhr.send();
}

/* ----------------------------------------------------------
 * 13. PUT /api/scenes/{id} —— 更新/回存场景
 *     请求体 JSON：{ "scene": { ...完整 scene.json... } }
 * -------------------------------------------------------- */
function apiUpdateScene() {
  var base = readBase();
  var sid = document.getElementById('sceneId').value;
  if (!sid) { alert('请填写 sceneId'); return; }
  var raw = document.getElementById('sceneJson').value;
  var sceneObj;
  try {
    sceneObj = JSON.parse(raw);
  } catch (e) {
    alert('scene JSON 格式错误：' + e.message);
    return;
  }
  var xhr = new XMLHttpRequest();
  xhr.open('PUT', base + '/scenes/' + sid);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onload = function () {
    showResult('PUT /api/scenes/' + sid + ' (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('PUT /api/scenes/{id}', xhr); };
  xhr.send(JSON.stringify({ scene: sceneObj }));
}

/* ----------------------------------------------------------
 * 14. GET /api/scenes/meta/catalog —— 品类与房间尺寸预设
 * -------------------------------------------------------- */
function apiGetCatalog() {
  var base = readBase();
  var xhr = new XMLHttpRequest();
  xhr.open('GET', base + '/scenes/meta/catalog');
  xhr.onload = function () {
    showResult('GET /api/scenes/meta/catalog (' + xhr.status + ')', xhr.responseText);
  };
  xhr.onerror = function () { netError('GET /api/scenes/meta/catalog', xhr); };
  xhr.send();
}

/* ============================================================
 * 端到端串联示例：创建项目 → 上传图片 → 轮询分析 → 生成场景
 * 用回调 + setInterval 串联，保持过程式（不使用 Promise 链）
 * ============================================================ */

/* 轮询分析，直到 done / failed 后回调 onDone */
function pollAnalysis(imageId, onDone) {
  var base = readBase();
  var timer = setInterval(function () {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', base + '/images/' + imageId + '/analysis');
    xhr.onload = function () {
      var data;
      try { data = JSON.parse(xhr.responseText); } catch (e) { data = {}; }
      showResult('流程③ 轮询分析 (status=' + (data.status || '?') + ')', xhr.responseText);
      if (data.status === 'done' || data.status === 'failed') {
        clearInterval(timer);
        if (data.status === 'done') {
          onDone();
        } else {
          alert('分析失败：' + (data.error || '未知错误'));
        }
      }
    };
    xhr.onerror = function () { clearInterval(timer); netError('流程③ 轮询分析', xhr); };
    xhr.send();
  }, 1500);
}

/* 一键跑通完整流程（需先在「上传图片文件」选好图） */
function runDemoFlow() {
  var base = readBase();
  var fileInput = document.getElementById('imageFile');
  if (!fileInput.files.length) { alert('请先在「上传图片文件」选择一张图，再点一键流程'); return; }

  // ① 创建项目
  var createXhr = new XMLHttpRequest();
  createXhr.open('POST', base + '/projects');
  createXhr.setRequestHeader('Content-Type', 'application/json');
  createXhr.onload = function () {
    var proj;
    try { proj = JSON.parse(createXhr.responseText); } catch (e) { proj = {}; }
    showResult('流程① 创建项目', createXhr.responseText);
    var pid = proj.id;
    if (!pid) { alert('创建项目失败，无法继续'); return; }

    // ② 上传图片（project_id 走 query）
    var fd = new FormData();
    fd.append('file', fileInput.files[0]);
    var upXhr = new XMLHttpRequest();
    upXhr.open('POST', base + '/images/upload?project_id=' + encodeURIComponent(pid));
    upXhr.onload = function () {
      var img;
      try { img = JSON.parse(upXhr.responseText); } catch (e) { img = {}; }
      showResult('流程② 上传图片', upXhr.responseText);
      var iid = img.id;
      if (!iid) { alert('上传图片失败，无法继续'); return; }

      // ③ 轮询分析 → ④ 生成场景
      pollAnalysis(iid, function () {
        var genXhr = new XMLHttpRequest();
        genXhr.open('POST', base + '/scenes/generate');
        genXhr.setRequestHeader('Content-Type', 'application/json');
        genXhr.onload = function () {
          showResult('流程④ 生成场景', genXhr.responseText);
        };
        genXhr.onerror = function () { netError('流程④ 生成场景', genXhr); };
        genXhr.send(JSON.stringify({ image_id: iid }));
      });
    };
    upXhr.onerror = function () { netError('流程② 上传图片', upXhr); };
    upXhr.send(fd);
  };
  createXhr.onerror = function () { netError('流程① 创建项目', createXhr); };
  createXhr.send(JSON.stringify({ name: 'Demo自动流程_' + Date.now() }));
}
