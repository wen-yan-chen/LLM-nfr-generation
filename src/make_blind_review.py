# -*- coding: utf-8 -*-
"""
生成盲评材料：
- 选 3 条测试 FR（借阅列表、留言板评论、多语言切换）
- 每条取 A/B/C 三种生成结果，清理后打乱顺序
- 输出匿名评分表 + CSV + 映射 key
用法：python make_blind_review.py
"""

import json, random, csv, re

RESULTS_PATH = "results.json"
MD_OUT = "blind_review.md"
CSV_OUT = "blind_review_scores.csv"
KEY_OUT = "blind_review_key.json"
SEED = 20261026

# 选这 3 条测试 FR
TARGET_FRS = [
    "借阅者应能查看自己当前借阅的图书列表",
    "系统应支持访客浏览留言板中的评论",
    "系统应支持多语言界面切换",
]

ANALYSIS_PREFIX = re.compile(
    r"^(功能场景分析|质量属性分析|经验参考与创新|需求生成|非功能需求如下|分析[:：]?|说明[:：]?)"
)


def postprocess(text):
    """只保留需求生成之后的列表项"""
    lines = []
    all_lines = text.splitlines()
    start_idx = 0
    for i, line in enumerate(all_lines):
        if re.search(r"(需求生成|非功能需求如下|NFR列表|非功能需求列表)", line):
            start_idx = i + 1
            break
    for raw in all_lines[start_idx:]:
        line = raw.strip()
        if not line:
            continue
        if ANALYSIS_PREFIX.match(line):
            continue
        if re.match(r"^(以下是|基于|综上所述|总结|根据|好的|当然|注意|上述)", line):
            continue
        line = re.sub(r"^[\*\-\u2022\d\.\)、\s]+", "", line)
        line = re.sub(r"^[`#>\s]+|[`#>\s]+$", "", line)
        if len(line) < 6:
            continue
        lines.append(line)
    seen, out = set(), []
    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def main():
    with open(RESULTS_PATH, encoding="utf-8") as f:
        results = json.load(f)

    # 按 test_fr 找到目标条目
    selected = []
    for fr in TARGET_FRS:
        hit = next((p for p in results if p["test_fr"] == fr), None)
        if hit is None:
            print(f"[警告] 未找到测试 FR：{fr}")
            continue
        selected.append(hit)

    # 构造匿名方案
    items = []
    for p in selected:
        for cond in ["A", "B", "C"]:
            lines = postprocess(p[f"gen_{cond}"])
            items.append({
                "fr": p["test_fr"],
                "cond": cond,
                "lines": lines,
            })

    random.seed(SEED)
    random.shuffle(items)

    # 分配编号
    for i, item in enumerate(items, 1):
        item["id"] = f"S{i:02d}"

    # ===== 1. 写 Markdown 评分表 =====
    md = []
    md.append("# 非功能需求生成结果盲评表\n")
    md.append("评分说明：请对每个方案按 1—5 分评价三个维度，不要猜测方案来源。\n")
    md.append("| 维度 | 1 分 | 3 分 | 5 分 |")
    md.append("|---|---|---|---|")
    md.append("| 完整性 | 严重缺失必要 NFR 要素 | 覆盖主要质量属性但有不足 | 全面覆盖，约束具体 |")
    md.append("| 准确性 | 术语混乱、偏离规范 | 基本符合但少量不当 | 专业术语准确、符合软件工程规范 |")
    md.append("| 可测试性 | 几乎无定量指标 | 部分可验证 | 大部分有明确量化指标和验证方法 |\n")
    md.append("---\n")

    for item in items:
        md.append(f"## 方案 {item['id']}\n")
        md.append(f"**测试功能需求：** {item['fr']}\n")
        md.append("**生成的非功能需求：**\n")
        if item["lines"]:
            for j, line in enumerate(item["lines"], 1):
                md.append(f"{j}. {line}")
        else:
            md.append("（无有效 NFR 条目）")
        md.append("\n**评分：**\n")
        md.append("| 完整性 | 准确性 | 可测试性 | 备注 |")
        md.append("|---|---|---|---|")
        md.append("| ___ / 5 | ___ / 5 | ___ / 5 |  |")
        md.append("\n---\n")

    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"已生成盲评表：{MD_OUT}")

    # ===== 2. 写 CSV 评分模板 =====
    with open(CSV_OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["方案编号", "测试FR", "完整性(1-5)", "准确性(1-5)", "可测试性(1-5)", "备注"])
        for item in items:
            w.writerow([item["id"], item["fr"], "", "", "", ""])
    print(f"已生成评分 CSV：{CSV_OUT}")

    # ===== 3. 写映射 key =====
    key = {item["id"]: {"test_fr": item["fr"], "condition": item["cond"]} for item in items}
    with open(KEY_OUT, "w", encoding="utf-8") as f:
        json.dump(key, f, ensure_ascii=False, indent=2)
    print(f"已生成映射 key：{KEY_OUT}（评完再看！）")

    # 控制台提示
    print("\n盲评流程：")
    print("1. 打开 blind_review.md，逐个方案打分，填到 blind_review_scores.csv")
    print("2. 或直接打印 blind_review.md 手写评分")
    print("3. 全部评完后，再打开 blind_review_key.json 对照 A/B/C")
    print("4. 用下面的汇总表算平均分")


if __name__ == "__main__":
    main()