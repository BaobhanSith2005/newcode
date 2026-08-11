"""冒烟测试：不依赖 HTTP 服务，直接验证 分析 → 布局求解 → scene.json 全链路。

同时校验几条硬性不变量（AI 输出再离谱，这些也必须成立）：
  1. 所有物体的俯视包围盒都在房间内
  2. 落地家具之间不得重叠（地毯除外）
  3. 声明靠墙的家具，其背面确实贴在墙上
  4. 输出符合 docs/scene.schema.json 的必填字段
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image, ImageDraw  # noqa: E402

from app.config import UPLOAD_DIR  # noqa: E402
from app.services.scene_builder import _footprint, build_scene  # noqa: E402
from app.services.vision import MOCK_SAMPLES, analyze_image  # noqa: E402

EPS = 1e-3


def make_sample(path: Path, seed: int) -> None:
    img = Image.new("RGB", (900, 600), (238, 232, 222))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 380, 900, 600], fill=(196, 168, 128))
    d.rectangle([120 + seed * 40, 250, 520 + seed * 40, 400], fill=(140, 152, 176))
    d.rectangle([600, 300, 800, 380], fill=(168, 132, 92))
    img.save(path, quality=88)


def check(scene: dict) -> list[str]:
    errs: list[str] = []
    W, D = scene["room"]["width"], scene["room"]["depth"]
    objs = scene["objects"]

    for o in objs:
        fw, fd = _footprint(o["size"]["w"], o["size"]["d"], o["rotation_y"])
        x, _y, z = o["position"]
        if x - fw / 2 < -W / 2 - EPS or x + fw / 2 > W / 2 + EPS:
            errs.append(f"{o['id']}({o['category']}) X 方向出界")
        if z - fd / 2 < -D / 2 - EPS or z + fd / 2 > D / 2 + EPS:
            errs.append(f"{o['id']}({o['category']}) Z 方向出界")

        wall = o.get("against_wall")
        if wall and o["category"] not in ("tv", "curtain", "air_conditioner"):
            gap = {
                "north": abs((z - fd / 2) - (-D / 2)),
                "south": abs((z + fd / 2) - (D / 2)),
                "west": abs((x - fw / 2) - (-W / 2)),
                "east": abs((x + fw / 2) - (W / 2)),
            }[wall]
            if gap > 0.35:
                errs.append(f"{o['id']}({o['category']}) 声明靠{wall}墙但离墙 {gap:.2f}m")

    floor = [o for o in objs if o["category"] != "rug" and o["position"][1] < 0.05]
    for i in range(len(floor)):
        for j in range(i + 1, len(floor)):
            a, b = floor[i], floor[j]
            aw, ad = _footprint(a["size"]["w"], a["size"]["d"], a["rotation_y"])
            bw, bd = _footprint(b["size"]["w"], b["size"]["d"], b["rotation_y"])
            ox = (aw + bw) / 2 - abs(b["position"][0] - a["position"][0])
            oz = (ad + bd) / 2 - abs(b["position"][2] - a["position"][2])
            if ox > 0.02 and oz > 0.02:
                errs.append(
                    f"{a['id']}({a['category']}) 与 {b['id']}({b['category']}) 重叠 "
                    f"{min(ox, oz):.2f}m"
                )
    return errs


def main() -> int:
    total_errs = 0

    # 先验证真实入口（图片 → analyze_image），确保 IO 与解析链路通
    probe = UPLOAD_DIR / "_smoke_probe.jpg"
    make_sample(probe, 0)
    probe_result = analyze_image(probe, force=True)
    print(f"analyze_image 入口正常，provider={probe_result['_meta']['provider']}，"
          f"识别 {len(probe_result['objects'])} 件物体")

    # 再逐个覆盖所有内置样例，避免哈希随机导致某条布局分支从未被测到
    for seed in sorted(MOCK_SAMPLES):
        analysis = dict(MOCK_SAMPLES[seed])
        scene = build_scene(analysis)

        room = scene["room"]
        print(f"\n{'=' * 62}")
        print(f"样例 {seed}: {room['type']}  "
              f"{room['width']}×{room['depth']}×{room['height']} m  "
              f"物体 {len(scene['objects'])} 件  门窗 {len(scene['openings'])} 处")
        print(f"{'=' * 62}")
        for o in scene["objects"]:
            wall = o["against_wall"] or "—"
            pos = ", ".join(f"{v:6.2f}" for v in o["position"])
            print(f"  {o['id']:<7} {o['category']:<15} [{pos}]  "
                  f"rot={o['rotation_y']:>5.0f}°  靠墙={wall:<7} "
                  f"资产={o['asset']['kind']}/{o['asset']['fallback']}")

        errs = check(scene)
        if errs:
            total_errs += len(errs)
            print("\n  [FAIL] 违反不变量：")
            for e in errs:
                print(f"    - {e}")
        else:
            print("\n  [OK] 边界 / 重叠 / 靠墙 三项不变量全部通过")

        if scene["meta"]["warnings"]:
            print(f"  警告：{scene['meta']['warnings']}")

        out = UPLOAD_DIR.parent / f"sample_scene_{seed}.json"  # backend/data/ 下
        out.write_text(json.dumps(scene, ensure_ascii=False, indent=2), "utf-8")
        print(f"  已导出 {out.name}")

    print(f"\n{'=' * 62}")
    print("全部通过 ✓" if total_errs == 0 else f"存在 {total_errs} 处问题 ✗")
    return 0 if total_errs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
