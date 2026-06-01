"""Simple async load test for /api/v1/ask-agentic.

Usage:
    uv run python scripts/load_test.py

This fires 100 requests with 10 concurrent connections.
Prints per-request status and a final summary.
"""
import asyncio
import time
from typing import List, Tuple

import httpx

# EKS LoadBalancer URL
BASE_URL = "http://ae18980d895d74b308f007e777bc185a-1762723266.us-east-1.elb.amazonaws.com"
ENDPOINT = f"{BASE_URL}/api/v1/ask-agentic"

# Test configuration
TOTAL_REQUESTS = 100
CONCURRENCY = 5  # max simultaneous requests (lowered to avoid OOM under Bedrock load)
TIMEOUT = 60.0

QUERIES = [
    "What is transformer architecture?",
    "Explain the attention mechanism in deep learning",
    "What is policy gradient in reinforcement learning?",
    "How does vector search work?",
    "What is BM25 ranking?",
]


async def make_request(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    req_num: int,
) -> Tuple[int, float, str]:
    """Fire a single request. Returns (status_code, elapsed_seconds, error_or_ok)."""
    query = QUERIES[req_num % len(QUERIES)]
    async with sem:
        start = time.perf_counter()
        try:
            resp = await client.post(
                ENDPOINT,
                json={"query": query},
                headers={"Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            elapsed = time.perf_counter() - start
            return resp.status_code, elapsed, ""
        except Exception as e:
            elapsed = time.perf_counter() - start
            return 0, elapsed, str(e)


async def main() -> None:
    print(f"Load test: {TOTAL_REQUESTS} requests → {ENDPOINT}")
    print(f"Concurrency: {CONCURRENCY}  |  Timeout: {TIMEOUT}s\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    results: List[Tuple[int, float, str]] = []

    async with httpx.AsyncClient() as client:
        # Health check first
        try:
            r = await client.get(f"{BASE_URL}/api/v1/health", timeout=10)
            print(f"Health check: {r.status_code} {r.json().get('status', 'unknown')}")
        except Exception as e:
            print(f"Health check FAILED: {e}")
            return

        # Fire all requests
        tasks = [make_request(client, sem, i) for i in range(TOTAL_REQUESTS)]
        start_all = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_elapsed = time.perf_counter() - start_all

    # Summarize
    codes = [c for c, _, _ in results]
    times = [t for _, t, _ in results if t > 0]
    errors = [e for _, _, e in results if e]
    success_200 = codes.count(200)
    non_200 = [c for c in codes if c != 200 and c != 0]
    timeouts = errors.count("timed out")

    print(f"\n{'='*60}")
    print("LOAD TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total requests:      {TOTAL_REQUESTS}")
    print(f"HTTP 200 OK:         {success_200}")
    print(f"HTTP non-200:        {len(non_200)}  ({set(non_200) if non_200 else 'none'})")
    print(f"Network errors:      {len(errors) - timeouts}")
    print(f"Timeouts:            {timeouts}")
    print(f"\nTiming:")
    print(f"  Total wall time:   {total_elapsed:.2f}s")
    print(f"  Req/sec:           {TOTAL_REQUESTS / total_elapsed:.2f}")
    print(f"  Min response:      {min(times):.2f}s")
    print(f"  Max response:      {max(times):.2f}s")
    print(f"  Avg response:      {sum(times) / len(times):.2f}s")
    print(f"  P50 (median):      {sorted(times)[len(times)//2]:.2f}s")
    print(f"  P95:               {sorted(times)[int(len(times)*0.95)]:.2f}s")
    print(f"{'='*60}")

    if errors:
        print("\nFirst 5 errors:")
        for e in errors[:5]:
            print(f"  - {e[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
