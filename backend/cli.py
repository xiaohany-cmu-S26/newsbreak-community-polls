"""Run the full pipeline on a pasted article and print the trace.

  .venv/bin/python -m backend.cli path/to/article.txt [--url URL] [--city "Mountain View, CA"] [--fresh]

File format: first line = headline, rest = body. --fresh deletes any cached result first."""
import argparse
import json
import sys
import time

from backend.agent.pipeline import get_or_create_poll, article_id_from_url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--url", default="")
    ap.add_argument("--city", default="", help="hint like 'Mountain View, CA'")
    ap.add_argument("--fresh", action="store_true", help="delete this article's cached verdict (and its poll if no other article shares it) and re-run the agent")
    ap.add_argument("--json", action="store_true", help="print only the final JSON")
    args = ap.parse_args()

    raw = open(args.file).read().strip().split("\n", 1)
    headline = raw[0].strip()
    body = raw[1].strip() if len(raw) > 1 else ""
    url = args.url or f"file://{args.file}"
    aid = article_id_from_url(url)

    log = (lambda m: None) if args.json else (lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True))
    t0 = time.time()
    r = get_or_create_poll({"article_id": aid, "url": url, "headline": headline, "text": body,
                            "city_hint": args.city}, log=log, force=args.fresh)
    if not args.json:
        print(f"\n--- done in {time.time() - t0:.1f}s ---")
    print(json.dumps({k: v for k, v in r.items() if k != "trace"}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
