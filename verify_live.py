"""真实环境验证工具：读取 dist/config.json 中配置的所有站点，逐一真实查询验证。

用法：python verify_live.py
输出每个站点的查询结果；存在失败站点时退出码为 1。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.worker import fetch_entry  # noqa: E402


def main() -> int:
    base = os.path.dirname(os.path.abspath(__file__))
    # 优先 dist/config.json（本地打包交付），其次根目录 config.json（源码运行/开源用法）
    cfg_path = None
    for cand in (os.path.join(base, "dist", "config.json"),
                 os.path.join(base, "config.json")):
        if os.path.exists(cand):
            cfg_path = cand
            break
    if cfg_path is None:
        print("未找到配置文件（dist/config.json 或 config.json）")
        return 2
    with open(cfg_path, encoding="utf-8") as f:
        data = json.load(f)
    entries = [e for e in data.get("providers", []) if e.get("enabled", True)]
    if not entries:
        print("config.json 中没有启用的站点。")
        return 2

    print(f"共 {len(entries)} 个站点，开始真实查询…\n")
    all_ok = True
    for e in entries:
        info = fetch_entry(e)
        name = info.display_name or e.get("display_name")
        ok = "OK " if info.ok else "FAIL"
        print(f"[{ok}] {name}")
        print(f"      总额={info.total} 已用={info.used} 剩余={info.remaining} {info.currency}")
        if info.extra:
            print(f"      其他={info.extra}")
        if not info.ok:
            print(f"      错误：{info.message}")
        print(f"      耗时={getattr(info, '_elapsed', '?')}s")
        if not info.ok:
            all_ok = False

    print(f"\n结果：{'全部站点查询成功' if all_ok else '存在失败的站点'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
