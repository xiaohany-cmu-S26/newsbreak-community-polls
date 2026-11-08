"""Triage evaluation: precision / recall on hand-labeled local articles.

  .venv/bin/python -m eval.run_triage_eval [--limit N] [--mock]

Reads eval/labeled_articles.jsonl. Each row: {"id", "url", "headline", "summary", "label": "pollable"|"not_pollable", "city", "notes"}.
If eval/articles/<id>.txt exists (hand-pasted body), it is used instead of the summary.
Results are written to eval/results/triage_<timestamp>.json and a table is printed."""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.agent import llm  # noqa: E402
from backend.agent.triage import triage  # noqa: E402


def load_rows(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def body_for(row):
    p = os.path.join(ROOT, "eval", "articles", f"{row['id']}.txt")
    if os.path.exists(p):
        txt = open(p).read().strip().split("\n", 1)
        return (txt[1] if len(txt) > 1 else txt[0]), "body"
    return row["summary"], "summary"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--file", default=os.path.join(ROOT, "eval", "labeled_articles.jsonl"))
    args = ap.parse_args()

    rows = load_rows(args.file)
    if args.limit:
        rows = rows[:args.limit]
    usage = llm.Usage()
    results = []
    tp = fp = fn = tn = 0
    print(f"{'id':>14}  {'label':<12} {'pred':<12} {'src':<7} headline")
    for r in rows:
        text, src = body_for(r)
        t0 = time.time()
        try:
            out = triage(r["headline"], text, usage, city_hint=r.get("city", ""))
        except Exception as e:  # keep going; count as error
            out = {"pollable": None, "category": "error", "reason": str(e)}
        pred = out["pollable"]
        gold = r["label"] == "pollable"
        if pred is True and gold: tp += 1
        elif pred is True and not gold: fp += 1
        elif pred is False and gold: fn += 1
        elif pred is False and not gold: tn += 1
        mark = "" if pred == gold else "  <-- MISS"
        print(f"{r['id']:>14}  {r['label']:<12} {str(pred):<12} {src:<7} {r['headline'][:70]}{mark}")
        results.append({**r, "pred": pred, "category": out.get("category"), "reason": out.get("reason"),
                        "source": src, "secs": round(time.time() - t0, 2)})

    n = len(rows)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    acc = (tp + tn) / n if n else 0.0
    summary = {"n": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 3),
               "recall": round(rec, 3), "f1": round(f1, 3), "accuracy": round(acc, 3),
               "mock": llm.MOCK, "model": llm.TRIAGE_MODEL, "usage": usage.summary()}
    print("\n" + json.dumps(summary, indent=2))
    os.makedirs(os.path.join(ROOT, "eval", "results"), exist_ok=True)
    out_path = os.path.join(ROOT, "eval", "results", f"triage_{time.strftime('%Y%m%d_%H%M%S')}.json")
    json.dump({"summary": summary, "rows": results}, open(out_path, "w"), indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
