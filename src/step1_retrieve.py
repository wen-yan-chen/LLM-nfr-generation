import json, random
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ===== 配置 =====
DATA_PATH = "data.json"
TEST_SIZE = 7
K = 5
LAMBDA = 0.7
SEED = 42

# ===== 1. 加载与划分 =====
with open(DATA_PATH, encoding="utf-8") as f:
    data = json.load(f)

random.seed(SEED)
idx = list(range(len(data)))
random.shuffle(idx)
test_data = [data[i] for i in idx[:TEST_SIZE]]
case_lib = [data[i] for i in idx[TEST_SIZE:]]

print(f"案例库 {len(case_lib)} 条，测试集 {len(test_data)} 条")
print("\n测试集 FR：")
for t in test_data:
    print(" -", t["fr"])

# ===== 2. 向量化案例库 =====
# bge-small-zh-v1.5 很小，CPU 也能跑
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
lib_fr = [d["fr"] for d in case_lib]
lib_emb = model.encode(lib_fr, normalize_embeddings=True)

# ===== 3. 检索 + MMR =====
def retrieve_mmr(query, k=K, lam=LAMBDA):
    q_emb = model.encode([query], normalize_embeddings=True)[0]
    sims = lib_emb @ q_emb  # 已归一化，点积=余弦相似度
    selected = []
    candidates = list(range(len(lib_fr)))
    while len(selected) < k and candidates:
        if not selected:
            best = max(candidates, key=lambda i: sims[i])
        else:
            def mmr(i):
                # 与已选案例的最大相似度
                max_sim = max(float(lib_emb[i] @ lib_emb[j]) for j in selected)
                return lam * float(sims[i]) - (1 - lam) * max_sim
            best = max(candidates, key=mmr)
        selected.append(best)
        candidates.remove(best)
    return selected

# ===== 4. 提示模板（文献五段式精简版） =====
PROMPT_TEMPLATE = """你是一位资深的需求分析师，具有10年以上软件需求工程经验，精通ISO/IEC 25010软件标准。基于你的专业知识，结合一些历史项目经验，为以下功能需求设计非功能需求：

[新功能需求]：{fr}

[历史案例]：
{cases}

请按以下步骤进行分析和生成：
1. 功能场景分析——分析功能特征和使用场景；
2. 质量属性分析——基于ISO/IEC 25010评估相关质量属性（性能效率、可用性、可靠性、安全性等）；
3. 经验参考与创新——参考历史经验并结合创新思考；
4. 需求生成——输出规范、可测试的非功能需求。

按照列表形式输出非功能需求描述，确保每条需求具体可度量，不输出任何其他内容。请记住，你的分析结果对该软件系统的成败至关重要，请务必认真分析！"""

PROMPT_NO_CASE = """你是一位资深的需求分析师，具有10年以上软件需求工程经验，精通ISO/IEC 25010软件标准。请为以下功能需求设计非功能需求：

[新功能需求]：{fr}

请按以下步骤进行分析和生成：
1. 功能场景分析；
2. 质量属性分析；
3. 需求生成——输出规范、可测试的非功能需求。

按照列表形式输出非功能需求描述，确保每条需求具体可度量，不输出任何其他内容。请记住，你的分析结果对该软件系统的成败至关重要，请务必认真分析！"""

def format_cases(indices):
    s = ""
    for rank, i in enumerate(indices, 1):
        s += f"案例{rank}：\nFR：{case_lib[i]['fr']}\nNFR：\n"
        for n in case_lib[i]["nfr"]:
            s += f"  - {n}\n"
    return s

# ===== 5. 为每个测试 FR 生成 3 个条件的提示 =====
out = []
for t in test_data:
    fr = t["fr"]
    # A: 无检索
    prompt_a = PROMPT_NO_CASE.format(fr=fr)
    # B: top1
    sel_b = retrieve_mmr(fr, k=1)
    prompt_b = PROMPT_TEMPLATE.format(fr=fr, cases=format_cases(sel_b))
    # C: MMR top5
    sel_c = retrieve_mmr(fr, k=K)
    prompt_c = PROMPT_TEMPLATE.format(fr=fr, cases=format_cases(sel_c))

    out.append({
        "test_fr": fr,
        "reference_nfr": t["nfr"],
        "retrieved_fr_C": [case_lib[i]["fr"] for i in sel_c],
        "prompt_A": prompt_a,
        "prompt_B": prompt_b,
        "prompt_C": prompt_c,
    })

with open("prompts.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("\n已生成 prompts.json")
print("先看第一条测试 FR 的 C 条件提示：\n")
print(out[0]["prompt_C"][:1200])