#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门口播脚本工坊 (mcd-script-forge)
2026 麦当劳程序员创意开发大赛参赛作品 · WorkBuddy 辅助开发

从麦当劳中国 MCP 数据（菜单/券池/计价）生成短视频口播三件套：
  script.md      口播全文（0.0s 精确时间轴 + 拍摄提示）
  storyboard.csv 分镜表（镜号/时长/画面建议/口播/字幕）
  captions.srt   SRT 字幕（时间轴按节拍切好）

用法：
  # Demo 模式（无需 MCP Token）
  python mcd_script_forge.py --demo --product "板烧鸡腿堡" --duration 15 --platform 抖音

  # 真实数据模式（由 WorkBuddy 先拉取 MCP 数据存为 mcp-data.json）
  python mcd_script_forge.py --data mcp-data.json --product "板烧鸡腿堡"

零第三方依赖，纯 Python 标准库；同一输入永远产出同一结果（种子化）。
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys

# ---------------- MCP 数据装载 ----------------

DEMO_DATA = {
    "_source": "demo-fixture（演示数据，非真实 MCP 返回）",
    "menu": {
        "板烧鸡腿堡": {"price": 26.5, "category": "汉堡", "calories_kcal": 529,
                       "tags": ["leg_grill", "no_fry", "classic"]},
        "巨无霸": {"price": 25.5, "category": "汉堡", "calories_kcal": 531,
                   "tags": ["icon", "double_beef"]},
        "麦辣鸡腿堡": {"price": 24.0, "category": "汉堡", "calories_kcal": 549,
                       "tags": ["spicy"]},
    },
    "coupons": [
        {"id": "CPN-DEMO-01", "title": "板烧鸡腿堡 优惠单件", "discount_price": 17.9,
         "applies_to": "板烧鸡腿堡", "expire_days": 5},
        {"id": "CPN-DEMO-02", "title": "中薯+饮料加购券", "discount_price": 9.9,
         "applies_to": "add-on", "expire_days": 3},
    ],
    "price_calc": {
        "板烧鸡腿堡": {"original": 26.5, "best_final": 17.9, "coupon_id": "CPN-DEMO-01",
                     "save": 8.6, "plan": "用券 CPN-DEMO-01 单点"},
    },
    "campaign_calendar": [
        {"name": "1024 程序员节", "date": "10-24", "hook": "程序员凭证件领巨无霸券"},
    ],
}


def load_data(path):
    """装载 MCP 数据；无文件时报错并提示 demo 模式。"""
    if not path:
        return DEMO_DATA
    if not os.path.exists(path):
        sys.exit(f"[!] 找不到 {path}。请先由 WorkBuddy 拉取 MCP 数据，或用 --demo 跑演示。")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key in ("menu", "coupons", "price_calc"):
        if key not in data:
            sys.exit(f"[!] {path} 缺少必需字段 `{key}`，字段说明见 MCP_INTEGRATION.md。")
    return data


# ---------------- 话术素材库（按 tag/情绪分桶） ----------------

HOOKS = {
    "price": [
        "别再原价吃麦当劳了！{product}我今天 {final} 块拿下。",
        "停！先别打开点餐软件——{product}现在有券，{final} 块。",
        "在麦当劳花原价的，都是没刷到这条视频的。",
    ],
    "scene": [
        "打工人的中午，就馋一口现烤鸡腿堡。",
        "加完班走进麦当劳的那一刻，全世界都原谅我了。",
    ],
    "festival": [
        "程序员节，麦当劳是真给程序员的。",
    ],
}

SELLS = {
    "leg_grill": "鸡腿是整块腿肉现烤的，不是油炸的，咬下去有烤痕的那种香。",
    "spicy": "辣度是标定的那种辣，爽但不烧胃。",
    "icon": "两层牛肉，麦门信仰本体。",
    "no_fry": "非油炸，吃完不背心理负担。",
    "classic": "上市这么多年还在卖的，就是不会错的味道。",
}

CTAS_COUPON = [
    "券就在麦当劳 App 里，领了再去，别原价付！",
    "打开麦当劳 App 搜「{product}」，{final} 块的券直接领。",
    "链接我放不上了，自己去 App 领券，{save_text}。",
]
CTAS_PLAIN = [
    "想吃的自己去 App 搜「{product}」，哪家近去哪家。",
    "今天的晚饭就它了，去最近的麦当劳，报「{product}」就行。",
]

# 每镜画面建议：映射到 MG 成熟风格（与 mcd-script-forge 配套的画面语言）
SHOT_SUGGESTIONS = {
    "HOOK": "大字报式钩子：产品特写怼脸 + 价格数字砸屏（红底黄字，两阶明暗扁平风）",
    "SELL": "产品分层解构动画：面包/肉饼/蔬菜逐层 exploded view（扁平矢量 MG）",
    "PRICE": "价格锚点对比条：原价划掉 → 券后价放大弹出 + 立省金额徽章",
    "CTA": "操作演示：手机界面录屏感 + App 领券路径箭头指引，结尾产品+logo 定格",
}


def pick(seq, rng):
    return seq[rng.randrange(len(seq))]


def fmt_price(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


# ---------------- 节拍表 ----------------

def build_beats(data, product, duration, platform, rng):
    """返回 [(t0, t1, 段名, 口播, 字幕)]，时间轴精确到 0.1s。"""
    menu = data["menu"].get(product)
    if not menu:
        sys.exit(f"[!] 数据里没有「{product}」。可用：{', '.join(data['menu'])}")
    calc = data["price_calc"].get(product, {})
    final = calc.get("best_final", menu["price"])
    save = calc.get("save", 0)
    save_text = f"一单省 {fmt_price(save)} 块" if save > 0 else "这单不亏"

    # 钩子：有券优先价格钩；无券切价值/场景钩（绝不编折扣，合规红线）
    if save > 0:
        hook = pick(list(HOOKS["price"]), rng)
    elif data.get("campaign_calendar"):
        hook = pick(HOOKS["festival"] + HOOKS["scene"], rng)
    else:
        hook = pick(HOOKS["scene"], rng)
    sell = " ".join(SELLS.get(t, "") for t in menu.get("tags", [])[:2]).strip() or SELLS["classic"]

    if duration <= 15:
        layout = [("HOOK", 0.0, 2.2), ("SELL", 2.2, 8.2), ("PRICE", 8.2, 12.0), ("CTA", 12.0, 15.0)]
    elif duration <= 30:
        layout = [("HOOK", 0.0, 2.5), ("SELL", 2.5, 12.5), ("PRICE", 12.5, 20.0),
                  ("PROOF", 20.0, 25.5), ("CTA", 25.5, 30.0)]
    else:
        sys.exit("[!] 时长支持 15 / 30 秒（短视频口播最优区间）")

    lines = {
        "HOOK": hook.format(product=product, final=fmt_price(final)),
        "SELL": sell,
        "PRICE": (f"原价 {fmt_price(calc.get('original', menu['price']))}，现在领券只要 {fmt_price(final)}，{save_text}。"
                  if save > 0 else
                  f"{fmt_price(calc.get('original', menu['price']))} 块，两层牛肉管饱，这个价不需要打折。"),
        "PROOF": f"我刚点了一单，实付 {fmt_price(final)} 块，到手还是那个量。",
        "CTA": pick(CTAS_COUPON if save > 0 else CTAS_PLAIN, rng).format(
            product=product, final=fmt_price(final), save_text=save_text),
    }
    beats = []
    for name, t0, t1 in layout:
        text = lines[name]
        if name == "PROOF":
            beats.append((t0, t1, name, text, f"实付 {fmt_price(final)} 元"))
            continue
        beats.append((t0, t1, name, text, text))
    return beats


# ---------------- 输出三件套 ----------------

def write_script_md(path, meta, beats):
    seg_hint = {"HOOK": "钩子：前 2 秒必须让手指停下", "SELL": "卖点：说人话，别念参数",
                "PRICE": "价格锚点：原价 vs 券后对比砸出来", "PROOF": "实证：晒实付截图增强可信",
                "CTA": "行动号召：告诉他现在去哪领"}
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 口播脚本 · {meta['product']}（{meta['duration']}s · {meta['platform']}）\n\n")
        f.write(f"- 数据来源：{meta['source']}\n")
        f.write(f"- 券后价：¥{meta['final']} ｜ 立省：¥{meta['save']}\n")
        f.write(f"- 生成：mcd-script-forge（确定性输出，同输入同结果）\n\n")
        f.write("## 时间轴全文\n\n")
        for t0, t1, name, speech, _ in beats:
            f.write(f"### [{t0:04.1f}s – {t1:04.1f}s] {name} · {seg_hint.get(name, '')}\n\n")
            f.write(f"> {speech}\n\n")
            if name == "HOOK":
                f.write("拍摄提示：台词第一个字就要开口，画面禁止空镜超过 0.3s。\n\n")
            if name == "CTA":
                f.write("拍摄提示：语速拉快，结尾定格 0.5s 留logo。\n\n")
        f.write("## 一段式朗读版（直接对着念）\n\n" + " ".join(b[3] for b in beats) + "\n")


def write_storyboard_csv(path, beats):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["镜号", "开始(s)", "结束(s)", "时长(s)", "段落", "画面建议", "口播", "字幕"])
        for i, (t0, t1, name, speech, sub) in enumerate(beats, 1):
            w.writerow([i, f"{t0:.1f}", f"{t1:.1f}", f"{t1-t0:.1f}", name,
                        SHOT_SUGGESTIONS.get(name, ""), speech, sub])


def fmt_srt_ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path, beats):
    with open(path, "w", encoding="utf-8") as f:
        for i, (t0, t1, _, _, sub) in enumerate(beats, 1):
            f.write(f"{i}\n{fmt_srt_ts(t0)} --> {fmt_srt_ts(t1 - 0.1)}\n{sub}\n\n")


# ---------------- 主入口 ----------------

def main():
    ap = argparse.ArgumentParser(description="麦门口播脚本工坊：MCP 数据 → 口播三件套")
    ap.add_argument("--demo", action="store_true", help="使用内置演示数据（无需 MCP Token）")
    ap.add_argument("--data", help="MCP 数据文件 mcp-data.json（WorkBuddy 拉取生成）")
    ap.add_argument("--product", default="板烧鸡腿堡", help="主推单品名")
    ap.add_argument("--duration", type=int, default=15, help="成片时长 15/30 秒")
    ap.add_argument("--platform", default="抖音", help="投放平台（影响话术语气）")
    ap.add_argument("--out", default="examples", help="输出目录")
    args = ap.parse_args()

    data = DEMO_DATA if args.demo else load_data(args.data)
    seed = int(hashlib.md5(f"{args.product}|{args.duration}|{args.platform}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    beats = build_beats(data, args.product, args.duration, args.platform, rng)
    calc = data["price_calc"].get(args.product, {})
    menu = data["menu"][args.product]
    meta = {
        "product": args.product, "duration": args.duration, "platform": args.platform,
        "source": data.get("_source", "麦当劳中国官方 MCP（mcp.mcd.cn）"),
        "final": calc.get("best_final", menu["price"]),
        "save": calc.get("save", 0),
    }

    os.makedirs(args.out, exist_ok=True)
    out_script = os.path.join(args.out, "script.md")
    out_board = os.path.join(args.out, "storyboard.csv")
    out_srt = os.path.join(args.out, "captions.srt")
    write_script_md(out_script, meta, beats)
    write_storyboard_csv(out_board, beats)
    write_srt(out_srt, beats)

    print(f"[✓] 三件套已生成 → {args.out}/")
    print(f"    口播脚本 {out_script}")
    print(f"    分镜表   {out_board}")
    print(f"    字幕     {out_srt}")
    print(f"    数据：{meta['source']}")


if __name__ == "__main__":
    main()
