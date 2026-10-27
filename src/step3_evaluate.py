# -*- coding: utf-8 -*-
"""
修复版评估：只保留“需求生成”之后的 NFR 列表项
用法：python step4_evaluate_fixed.py
输出：eval_report_fixed.md / eval_scores_fixed.csv
"""

import json, re, math, csv
from collections import Counter

RESULTS_PATH = "results.json"
MD_OUT = "eval_report_fixed.md"
CSV_OUT = "eval_scores_fixed.csv"

CAT_KW = {
    "性能": ["P95", "P99", "响应", "延迟", "并发", "吞吐", "ms", "秒"],
    "安全": ["加密", "认证", "权限", "脱敏", "HTTPS", "TLS", "审计", "敏感", "403", "401", "429"],
    "可靠": ["重试", "故障", "降级", "可用", "成功率", "容错", "幂等", "事务", "切换"],
    "可维护": ["日志", "配置", "回滚", "版本", "监控", "可维护", "告警"],
    "易用": ["界面", "提示", "无需", "直观", "分页", "空态", "点击"],
    "兼容": ["浏览器", "Chrome", "Firefox", "Safari", "响应式", "断点", "移动端", "像素"],
}

QUANT_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ms|毫秒|秒|分钟|小时|天|年|次|条|个|%|px|MB|GB|QPS|TPS|并发)",
    re.IGNORECASE,
)

ANALYSIS_PREFIX = re.compile(
    r"^(功能场景分析|质量属性分析|经验参考与创新|需求生成|非功能需求如下|分析[:：]?|说明[:：]?)"
)

def postprocess(text):
    """只保留需求生成之后的列表项"""
    lines = []
    # 先找到“需求生成”或“非功能需求如下”之后的内容
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
    # 去重
    seen, out = set(), []
    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def tokenize(text):
    return re.sub(r"[\s\W]+", "", text)


def ngram_counter(tokens, n):
    return Counter(tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1))


def bleu_score(ref, gen, max_n=4):
    if not gen or not ref:
        return 0.0
    precisions = []
    for n in range(1, max_n+1):
        rc, gc = ngram_counter(ref, n), ngram_counter(gen, n)
        overlap = sum((rc & gc).values())
        total = sum(gc.values())
        precisions.append((overlap + 1e-9) / (total + 1e-9))
    bp = 1.0 if len(gen) >= len(ref) else math.exp(1 - len(ref) / max(1, len(gen)))
    return bp * math.exp(sum(math.log(p) for p in precisions) / max_n)


def rouge_n_f1(ref, gen, n=1):
    rc, gc = ngram_counter(ref, n), ngram_counter(gen, n)
    overlap = sum((rc & gc).values())
    if overlap == 0:
        return 0.0
    p = overlap / sum(gc.values())
    r = overlap / sum(rc.values())
    return 2 * p * r / (p + r) if (p + r) else 0.0


def lcs_len(a, b):
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        cur = [0] * (n + 1)
        for j in range(1, n + 1):
            cur[j] = prev[j-1] + 1 if a[i-1] == b[j-1] else max(prev[j], cur[j-1])
        prev = cur
    return prev[n]


def rouge_l_f1(ref, gen):
    if not ref or not gen:
        return 0.0
    lcs = lcs_len(ref, gen)
    p = lcs / len(gen)
    r = lcs / len(ref)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def quant_ratio(lines):
    if not lines:
        return 0.0
    return sum(1 for l in lines if QUANT_PATTERN.search(l)) / len(lines)


def category_coverage(text):
    covered = sum(1 for kws in CAT_KW.values() if any(k in text for k in kws))
    return covered / len(CAT_KW)


def main():
    with open(RESULTS_PATH, encoding="utf-8") as f:
        results = json.load(f)

    rows = []
    for p in results:
        ref_text = " ".join(p["reference_nfr"])
        ref_tokens = tokenize(ref_text)
        row = {"test_fr": p["test_fr"]}
        for cond in ["A", "B", "C"]:
            gen_lines = postprocess(p[f"gen_{cond}"])
            gen_text = " ".join(gen_lines)
            gen_tokens = tokenize(gen_text)
            row[f"nfr_count_{cond}"] = len(gen_lines)
            row[f"quant_{cond}"] = round(quant_ratio(gen_lines), 4)
            row[f"coverage_{cond}"] = round(category_coverage(gen_text), 4)
            row[f"bleu_{cond}"] = round(bleu_score(ref_tokens, gen_tokens), 4)
            row[f"rouge1_{cond}"] = round(rouge_n_f1(ref_tokens, gen_tokens, 1), 4)
            row[f"rougeL_{cond}"] = round(rouge_l_f1(ref_tokens, gen_tokens), 4)
            row[f"gen_clean_{cond}"] = gen_lines
        rows.append(row)

    metrics = ["nfr_count", "quant", "coverage", "bleu", "rouge1", "rougeL"]
    metric_names = {
        "nfr_count": "NFR 条数", "quant": "可量化比例",
        "coverage": "类别覆盖率", "bleu": "BLEU",
        "rouge1": "ROUGE-1", "rougeL": "ROUGE-L",
    }
    summary = {c: {m: round(sum(r[f"{m}_{c}"] for r in rows) / len(rows), 4) for m in metrics}
               for c in ["A", "B", "C"]}

    md = ["# NFR 生成评估报告（修复版）\n", "## 一、整体平均指标\n"]
    md.append("| 指标 | A 无检索 | B top1 | C MMR top5 |")
    md.append("|---|---|---|---|")
    for m in metrics:
        md.append(f"| {metric_names[m]} | {summary['A'][m]} | {summary['B'][m]} | {summary['C'][m]} |")

    md.append("\n## 二、逐条明细\n")
    for i, r in enumerate(rows, 1):
        md.append(f"\n### {i}. {r['test_fr']}\n")
        md.append("| 条件 | NFR条数 | 可量化 | 类别覆盖 | BLEU | ROUGE-1 | ROUGE-L |")
        md.append("|---|---|---|---|---|---|---|")
        for cond, label in [("A", "A 无检索"), ("B", "B top1"), ("C", "C MMR top5")]:
            md.append(f"| {label} | {r[f'nfr_count_{cond}']} | {r[f'quant_{cond}']} | "
                      f"{r[f'coverage_{cond}']} | {r[f'bleu_{cond}']} | "
                      f"{r[f'rouge1_{cond}']} | {r[f'rougeL_{cond}']} |")
        md.append("\n**C 条件生成内容：**\n")
        for line in r["gen_clean_C"]:
            md.append(f"- {line}")

    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"已生成报告：{MD_OUT}")

    csv_fields = ["test_fr"] + [f"{m}_{c}" for c in ["A", "B", "C"] for m in metrics]
    with open(CSV_OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"已生成 CSV：{CSV_OUT}")

    print("\n" + "=" * 60)
    print(f"{'指标':<12} {'A 无检索':>10} {'B top1':>10} {'C MMR top5':>12}")
    print("-" * 60)
    for m in metrics:
        print(f"{metric_names[m]:<12} {summary['A'][m]:>10} {summary['B'][m]:>10} {summary['C'][m]:>12}")
    print("=" * 60)


if __name__ == "__main__":
    main()