"""Run all data integrity/leakage checks and print a PASS/FAIL table. Exit 1 if any fail.

Usage: .venv/bin/python pipelines/check_data.py
"""
import sys
import time

from data_checks import CHECKS


def main() -> int:
    rows, failed = [], 0
    for name, fn in CHECKS.items():
        t = time.time()
        try:
            ok, detail = fn()
        except Exception as e:  # a crashing check is a failure, reported not hidden
            ok, detail = False, f"ERROR {type(e).__name__}: {e}"
        failed += not ok
        rows.append(("PASS" if ok else "FAIL", name, f"{time.time() - t:.1f}s", detail))
    w = max(len(r[1]) for r in rows)
    print(f"{'RESULT':6}  {'CHECK':{w}}  TIME   DETAIL")
    for r in rows:
        print(f"{r[0]:6}  {r[1]:{w}}  {r[2]:>5}  {r[3]}")
    print(f"\n{len(rows) - failed}/{len(rows)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
