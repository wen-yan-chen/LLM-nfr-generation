# -*- coding: utf-8 -*-
"""
批量生成 A/B/C 三种条件的 NFR
用法：
    $env:DEEPSEEK_API_KEY="sk-xxx"
    python step2_generate.py
特性：
    - 断点续跑：中断后重跑会跳过已生成的条目
    - 自动重试：网络抖动自动重试 3 次
"""

import os, json, time, sys
from openai import OpenAI

PROMPTS_PATH = "prompts.json"
RESULTS_PATH = "results.json"
MODEL = "deepseek-chat"
TEMPERATURE = 0.9      # 论文推荐
TOP_P = 0.9
FREQ_PENALTY = 0.5     # 论文“惩罚系数”
MAX_RETRIES = 3

api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
if not api_key:
    print("错误：未设置 DEEPSEEK_API_KEY 环境变量")
    sys.exit(1)

client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

with open(PROMPTS_PATH, encoding="utf-8") as f:
    prompts = json.load(f)

# 断点续跑
if os.path.exists(RESULTS_PATH):
    with open(RESULTS_PATH, encoding="utf-8") as f:
        results = json.load(f)
    print(f"检测到 {RESULTS_PATH}，从上次进度继续")
else:
    results = prompts


def call_llm(prompt):
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                top_p=TOP_P,
                frequency_penalty=FREQ_PENALTY,
            )
            return resp.choices[0].message.content
        except Exception as e:
            wait = 2 ** attempt
            print(f"\n  [重试 {attempt+1}/{MAX_RETRIES}] {e}，等待 {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("多次重试仍失败")


for i, p in enumerate(results, 1):
    print(f"\n[{i}/{len(results)}] {p['test_fr']}")
    for cond in ["A", "B", "C"]:
        key = f"gen_{cond}"
        if p.get(key):
            print(f"  {cond}: 已存在，跳过")
            continue
        print(f"  {cond}: 生成中...", end="", flush=True)
        t0 = time.time()
        text = call_llm(p[f"prompt_{cond}"])
        p[key] = text
        print(f" 完成 ({time.time()-t0:.1f}s, {len(text)} 字)", flush=True)
        # 每完成一次就写盘，防中断丢失
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n全部完成，结果已保存到 {RESULTS_PATH}")