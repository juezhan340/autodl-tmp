# -*- coding: utf-8 -*-
"""收集"小模型领域适配"调研的证据底稿。

两步走：
  A. OpenAlex（直连，无代理）按 title+abstract 相关性检索候选论文，
     每个检索词取前 50 条，按标题去重；
  B. Semantic Scholar batch 接口（走 127.0.0.1:7897 代理）批量补引用数，
     每批 100 个 ID，一次请求就能拿到几百篇的引用数，避开单查限流。

输出：
  ev_candidates.json  去重后的候选论文（含引用数、年份、venue、arXiv ID）
  ev_by_query.json    每个检索词按引用数排序的结果
  ev_classics.json    指定经典论文的精确核对结果
"""
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

DATA = Path(r"C:\Users\洛涧北府\AppData\Local\Temp\hf_analyze")
MAILTO = "research-helper@example.com"

direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
proxied = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"})
)

QUERIES = [
    "domain adaptive pretraining language model",
    "domain specific small language model fine tuning",
    "parameter efficient fine tuning LoRA",
    "QLoRA quantized finetuning",
    "instruction tuning data selection small model",
    "knowledge distillation small language model",
    "group relative policy optimization LLM",
    "RLVR reinforcement learning verifiable reward language model",
    "curriculum learning language model post training",
    "data mixture optimization language model",
    "continual pretraining catastrophic forgetting LLM",
    "small language model survey efficient",
    "on-device small language model personalization",
    "smart home LLM agent task planning",
    "agentic tool use fine tuning small model",
    "multi-task instruction tuning data replay",
]

# 经典/必引核对（按 arXiv ID，S2 batch 直接给引用数）
CLASSICS = {
    "LoRA": "2106.09685",
    "QLoRA": "2305.14314",
    "LIMA": "2305.11206",
    "Don't Stop Pretraining (DAPT)": "2004.10964",
    "DeepSeekMath (GRPO)": "2402.03300",
    "DAPO": "2503.14476",
    "DeepSeek-R1": "2501.12948",
    "Dr.GRPO / R1-Zero-like": "2503.20783",
    "TinyLlama": "2401.02385",
    "phi-1 Textbooks": "2306.11644",
    "ODM online data mixing": "2312.02406",
    "How to Train Data-Efficient LLMs": "2405.07490",
    "warmup continual pretraining": "2308.08747",
    "SSR self-synthesized rehearsal": "2403.01244",
    "DPO": "2305.18290",
    "InstructGPT RLHF": "2203.02155",
    "PEFT survey": "2403.14608",
    "Tulu 3": "2411.15124",
    "Qwen2": "2407.10671",
    "Qwen2.5": "2412.15115",
    "OLMo": "2402.00838",
    "phi-3": "2404.14219",
    "Small LM survey (2409.15790)": "2409.15790",
    "Flan-T5 scaling instruction finetuning": "2210.11416",
    "Flan Collection": "2301.13688",
    "Self-Instruct": "2212.10560",
    "WizardLM Evol-Instruct": "2304.12244",
    "Magpie": "2406.08464",
    "AlpaGasus": "2307.08701",
    "DoReMi": "2305.10429",
    "RegMix": "2407.01492",
    "Data Mixing Laws": "2403.16952",
    "AdaRFT": "2504.05520",
    "DISCO": "2505.15074",
    "ADS 2606.22305（核查）": "2606.22305",
    "HDS 2606.24133（核查）": "2606.24133",
    "Entropy Pacing 2607.07178（核查）": "2607.07178",
    "Open-Reasoner-Zero": "2503.24290",
    "Logic-RL": "2502.14768",
}


def get(url, retries=4, opener=None):
    """带退避重试的 GET。"""
    opener = opener or direct
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-helper/1.0"})
            with opener.open(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                return {"error": str(e)[:160]}
            time.sleep(6 * (i + 1) if "429" in str(e) else 3 * (i + 1))
    return {}


def post_json(url, payload, retries=5):
    """向 Semantic Scholar batch 接口 POST，带重试。"""
    body = json.dumps(payload).encode("utf-8")
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "research-helper/1.0"},
            )
            with proxied.open(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            print(f"    batch retry {i + 1}: {str(e)[:90]}")
            if i == retries - 1:
                return {"error": str(e)[:160]}
            time.sleep(12 * (i + 1))
    return {}


def norm_title(s):
    """标题归一化，用于去重。"""
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum())


# ---------- 步骤 A：OpenAlex 相关性检索 ----------
print("== 步骤 A：OpenAlex 相关性检索 ==")
cand = {}   # key: 归一化标题 -> 记录
by_query = {}
for q in QUERIES:
    url = ("https://api.openalex.org/works?"
           + urllib.parse.urlencode({
               "filter": f"title_and_abstract.search:{q}",
               "per-page": 50,
               "mailto": MAILTO,
           }))
    d = get(url)
    rows = []
    for w in (d.get("results") or []):
        title = w.get("title") or ""
        key = norm_title(title)
        if not key:
            continue
        arxiv = ""
        for loc in (w.get("locations") or []):
            u = (loc.get("landing_page_url") or "")
            if "arxiv.org/abs/" in u:
                arxiv = u.rsplit("/", 1)[-1]
                break
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        rec = cand.get(key) or {
            "title": title,
            "year": w.get("publication_year"),
            "doi": doi,
            "arxiv": arxiv,
            "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
            "oa_citations": w.get("cited_by_count"),
            "queries": [],
        }
        if q not in rec["queries"]:
            rec["queries"].append(q)
        cand[key] = rec
        rows.append(key)
    by_query[q] = rows
    print(f"  {q}: +{len(rows)} 命中（累计去重 {len(cand)}）")
    time.sleep(0.4)

# ---------- 步骤 B：S2 batch 补引用数 ----------
print("== 步骤 B：Semantic Scholar batch 补引用数 ==")
ids = []
id_to_key = {}
for key, rec in cand.items():
    if rec["arxiv"]:
        sid, tag = f"ARXIV:{rec['arxiv']}", ("arxiv", rec["arxiv"])
    elif rec["doi"]:
        sid, tag = f"DOI:{rec['doi']}", ("doi", rec["doi"])
    else:
        # 没有 arXiv/DOI 的（主要是书籍章节等）跳过，引用数留空
        continue
    ids.append(sid)
    id_to_key[sid] = key
classic_ids = {f"ARXIV:{a}": name for name, a in CLASSICS.items()}
all_ids = ids + [i for i in classic_ids if i not in id_to_key]
print(f"  待查 {len(all_ids)} 篇（候选 {len(ids)} + 经典 {len(classic_ids)}）")

s2_map = {}
CHUNK = 100
for i in range(0, len(all_ids), CHUNK):
    chunk = all_ids[i:i + CHUNK]
    url = ("https://api.semanticscholar.org/graph/v1/paper/batch"
           "?fields=title,year,citationCount,venue,externalIds")
    res = post_json(url, {"ids": chunk})
    if isinstance(res, list):
        for sid, item in zip(chunk, res):
            s2_map[sid] = item or {}
        got = sum(1 for it in res if it)
        print(f"  批次 {i // CHUNK + 1}: {got}/{len(chunk)} 命中")
    else:
        print(f"  批次 {i // CHUNK + 1} 失败: {res}")
    time.sleep(6)

# 把 S2 数据并回候选
for sid, item in s2_map.items():
    if not item:
        continue
    if sid in id_to_key:
        rec = cand[id_to_key[sid]]
        rec["s2_title"] = item.get("title")
        rec["s2_year"] = item.get("year")
        rec["citations"] = item.get("citationCount")
        rec["s2_venue"] = item.get("venue")

classics_out = {}
for sid, name in classic_ids.items():
    item = s2_map.get(sid) or {}
    classics_out[name] = {
        "arxiv": sid.replace("ARXIV:", ""),
        "title": item.get("title"),
        "year": item.get("year"),
        "citations": item.get("citationCount"),
        "venue": item.get("venue"),
    }
print("  -- 经典核对 --")
for name, r in classics_out.items():
    print(f"  {name} | {r['citations'] if r['citations'] is not None else 'N/A'} 引 | {r['year']} | {str(r['title'])[:70]}")

# 每个检索词按引用数排序输出
ranked = {}
for q, keys in by_query.items():
    rows = [cand[k] for k in keys]
    rows.sort(key=lambda r: -(r.get("citations") or -1))
    ranked[q] = rows[:15]
    print("=" * 78)
    print("QUERY:", q)
    for r in rows[:8]:
        print(f"  {r.get('citations') if r.get('citations') is not None else '?':>6} 引 | {r.get('year')} | {r['title'][:74]}")
        print(f"          {r.get('s2_venue') or r.get('venue') or ''} | arXiv:{r.get('arxiv') or '-'} | DOI:{r.get('doi') or '-'}")

(DATA / "ev_candidates.json").write_text(json.dumps(list(cand.values()), ensure_ascii=False, indent=1), encoding="utf-8")
(DATA / "ev_by_query.json").write_text(json.dumps(ranked, ensure_ascii=False, indent=1), encoding="utf-8")
(DATA / "ev_classics.json").write_text(json.dumps(classics_out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved: ev_candidates.json / ev_by_query.json / ev_classics.json")
