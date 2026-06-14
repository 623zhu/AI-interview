"""run_eval.py — 跑 RAG 检索评测，输出指标 JSON + Markdown 对比表。

用法:
    cd backend

    # 1) 跑单次评测（默认读 golden_auto.jsonl）
    python -m eval.rag.run_eval --label baseline --no-rerank
    python -m eval.rag.run_eval --label with_rerank --rerank

    # 2) 用手工黄金集
    python -m eval.rag.run_eval --label manual_test --rerank --golden eval/rag/golden_manual.yaml

    # 3) 对比两次结果
    python -m eval.rag.run_eval --compare baseline with_rerank

产出:
    eval/rag/results/{label}.json   — 原始指标
    stdout                          — Markdown 对比表
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

GOLDEN_AUTO = Path(__file__).resolve().parent / "golden_auto.jsonl"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ── Load golden set ────────────────────────────────────────

def load_golden_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_golden_yaml(path: Path) -> list[dict]:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    records = []
    for item in raw:
        records.append({
            "query": item["query"],
            "positive_ids": item.get("must_include_ids") or item.get("positive_ids", []),
            "soft_ids": item.get("any_of_ids", []),
            "forbidden_ids": item.get("forbidden_ids", []),
            "skill_nodes": item.get("skill_nodes", []),
        })
    return records


def load_golden(path: Path) -> list[dict]:
    if path.suffix in (".yaml", ".yml"):
        return load_golden_yaml(path)
    return load_golden_jsonl(path)


# ── Metrics ────────────────────────────────────────────────

def compute_metrics(ranked_ids: list[str], gold: set[str], soft: set[str], k: int = 5) -> dict:
    top_k = ranked_ids[:k]
    top_10 = ranked_ids[:10]

    # recall@k
    recall = 1 if (gold & set(top_k)) else 0

    # hit@1
    hit1 = 1 if (top_k and top_k[0] in gold) else 0

    # mrr@10
    mrr = 0.0
    for i, rid in enumerate(top_10, 1):
        if rid in gold:
            mrr = 1.0 / i
            break

    # nDCG@k with soft relevance
    rels = []
    for rid in top_k:
        if rid in gold:
            rels.append(2)
        elif rid in soft:
            rels.append(1)
        else:
            rels.append(0)
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))
    ideal = sorted(rels, reverse=True)
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    ndcg = dcg / idcg if idcg > 0 else 0.0

    # forbidden penalty (count how many forbidden made it into top_k)
    # only relevant for manual golden sets
    return {"recall@5": recall, "hit@1": hit1, "mrr@10": mrr, "ndcg@5": ndcg}


# ── Evaluation runner ──────────────────────────────────────

async def run_evaluation(golden: list[dict], *, rerank: bool, k: int = 5) -> dict:
    from app.agent.rag import search_questions

    all_metrics: dict[str, list[float]] = {
        "recall@5": [], "hit@1": [], "mrr@10": [], "ndcg@5": [], "latency_ms": [],
    }
    errors = 0

    for i, case in enumerate(golden):
        query = case["query"]
        gold = set(case.get("positive_ids", []))
        soft = set(case.get("soft_ids") or case.get("skill_nodes") or [])

        t0 = time.perf_counter()
        try:
            results = await search_questions(
                query=query, k=10, rerank=rerank, over_fetch=30,
            )
        except Exception as e:
            print(f"  [{i+1}] ERROR: {e}")
            errors += 1
            continue
        dt_ms = (time.perf_counter() - t0) * 1000

        ranked_ids = [
            r.metadata.get("mysql_id", r.id)
            if isinstance(r.metadata, dict) else r.id
            for r in results
        ]

        m = compute_metrics(ranked_ids, gold, soft, k=k)
        for key in m:
            all_metrics[key].append(m[key])
        all_metrics["latency_ms"].append(dt_ms)

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(golden)}] ...")

    summary = {}
    for key, vals in all_metrics.items():
        if not vals:
            summary[key] = 0.0
            continue
        if key == "latency_ms":
            sorted_v = sorted(vals)
            summary["latency_p50"] = sorted_v[len(sorted_v) // 2]
            summary["latency_p95"] = sorted_v[int(len(sorted_v) * 0.95)]
            summary["latency_mean"] = statistics.mean(vals)
        else:
            summary[key] = round(statistics.mean(vals), 4)

    summary["total_cases"] = len(golden)
    summary["errors"] = errors
    summary["rerank"] = rerank
    return summary


# ── Compare ────────────────────────────────────────────────

def compare(labels: list[str]):
    results = {}
    for label in labels:
        path = RESULTS_DIR / f"{label}.json"
        if not path.exists():
            print(f"[ERROR] {path} 不存在，先用 --label {label} 跑一次")
            return
        with open(path, "r", encoding="utf-8") as f:
            results[label] = json.load(f)

    metrics_keys = ["recall@5", "hit@1", "mrr@10", "ndcg@5", "latency_p50", "latency_p95"]
    header = "| 配置 | " + " | ".join(metrics_keys) + " |"
    sep = "|" + "|".join(["---"] * (len(metrics_keys) + 1)) + "|"

    print("\n## RAG 评测对比\n")
    print(header)
    print(sep)
    for label, data in results.items():
        row = f"| {label} |"
        for k in metrics_keys:
            v = data.get(k, 0)
            if "latency" in k:
                row += f" {v:.0f}ms |"
            else:
                row += f" {v:.4f} |"
        print(row)
    print()


# ── Main ───────────────────────────────────────────────────

async def main_eval(label: str, rerank: bool, golden_path: Path):
    golden = load_golden(golden_path)
    if not golden:
        print(f"[ERROR] 黄金集为空: {golden_path}")
        return

    print(f"评测 '{label}' | rerank={rerank} | {len(golden)} cases | golden={golden_path.name}")
    summary = await run_evaluation(golden, rerank=rerank)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{label}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] 结果写入 {out_path}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG 检索评测")
    sub = parser.add_subparsers(dest="cmd")

    # run
    run_parser = sub.add_parser("run", help="跑一次评测")
    run_parser.add_argument("--label", required=True, help="本次评测标签，如 baseline / with_rerank")
    run_parser.add_argument("--rerank", action="store_true", default=False, help="启用 rerank")
    run_parser.add_argument("--no-rerank", action="store_true", default=False, help="禁用 rerank")
    run_parser.add_argument("--golden", type=str, default=None, help="黄金集路径")

    # compare
    cmp_parser = sub.add_parser("compare", help="对比多次评测结果")
    cmp_parser.add_argument("labels", nargs="+", help="要对比的 label 列表")

    args = parser.parse_args()

    if args.cmd == "compare":
        compare(args.labels)
    elif args.cmd == "run":
        golden_path = Path(args.golden) if args.golden else GOLDEN_AUTO
        use_rerank = args.rerank and not args.no_rerank
        asyncio.run(main_eval(args.label, use_rerank, golden_path))
    else:
        parser.print_help()