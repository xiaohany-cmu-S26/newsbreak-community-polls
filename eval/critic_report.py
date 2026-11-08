"""Critic statistics from the polls table: how many drafts were flagged, issue types, before/after examples.

  .venv/bin/python -m eval.critic_report"""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend import db  # noqa: E402


def main():
    polls = [p for p in db.list_polls(limit=1000) if "hand-seeded" not in str((p.get("usage") or {}).get("note", ""))]
    if not polls:
        print("no agent-generated polls in the database yet (hand-seeded demo polls are excluded)")
        return
    flagged = [p for p in polls if any(not c["passed"] for c in p["critic_log"])]
    types = Counter(i["type"] for p in polls for c in p["critic_log"] for i in c["issues"])
    passes = [p["critic_passes"] for p in polls]
    cost = sum((p.get("usage") or {}).get("cost_usd", 0) for p in polls)
    print(f"polls: {len(polls)}   first draft flagged: {len(flagged)} ({100*len(flagged)/len(polls):.0f}%)   "
          f"never passed: {sum(1 for p in polls if not p['critic_passed'])}")
    print(f"critic passes per poll: mean {sum(passes)/len(passes):.2f}, max {max(passes)}   total agent cost: ${cost:.2f}")
    print("issue types caught:", dict(types.most_common()))
    print("\n--- before / after examples ---")
    for p in flagged[:5]:
        log = p["critic_log"]
        first, last = log[0], log[-1]
        print(f"\n[{p['poll_id']}] {p['city']}")
        print(f"  BEFORE: {first['draft']['question']}")
        for i in first["issues"]:
            print(f"     critic ({i['type']}): {i['detail']}")
        print(f"  AFTER : {last['draft']['question']}  ({'PASS' if last['passed'] else 'still flagged'})")
        if first["draft"]["options"] != last["draft"]["options"]:
            print(f"  options before: {first['draft']['options']}")
            print(f"  options after : {last['draft']['options']}")


if __name__ == "__main__":
    main()
