"""Quick connectivity check for all external APIs."""

import asyncio
import sys
import socket
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings


async def check_openai(settings):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=10)
    page = await client.models.list()
    gpt_models = [m.id for m in page.data if "gpt" in m.id][:3]
    return f"OK — {len(page.data)} models available, e.g. {gpt_models}"


async def check_postgres(settings):
    import asyncio
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.postgres_database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()")).scalar()
    engine.dispose()
    return f"OK — {result[:40]}..."


async def check_redis(settings):
    import redis as redis_lib
    client = redis_lib.from_url(settings.redis.url, decode_responses=True, socket_connect_timeout=10)
    pong = client.ping()
    info = client.info("server")
    version = info.get("redis_version", "unknown")
    client.close()
    return f"OK — PONG={pong}, Redis {version}"


async def check_langfuse(settings):
    import httpx
    url = f"{settings.langfuse.host}/api/public/health"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
    return f"OK — {r.status_code} {r.json()}"


async def check_jina(settings):
    import httpx
    headers = {"Authorization": f"Bearer {settings.jina_api_key}", "Content-Type": "application/json"}
    payload = {"model": "jina-embeddings-v3", "input": ["hello world"], "dimensions": 1024}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://api.jina.ai/v1/embeddings", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    dims = len(data["data"][0]["embedding"])
    return f"OK — {dims}-dim embedding returned"


def check_postgres_ipv4(settings):
    """Resolve Postgres host and report IPv4 vs IPv6."""
    url = settings.postgres_database_url
    # Extract hostname between @ and /
    host = url.split("@")[1].split("/")[0].split(":")[0].split("?")[0]
    results = socket.getaddrinfo(host, 5432, proto=socket.IPPROTO_TCP)
    families = {socket.AF_INET: "IPv4", socket.AF_INET6: "IPv6"}
    resolved = [(families.get(r[0], str(r[0])), r[4][0]) for r in results]
    return host, resolved


async def main():
    settings = get_settings()
    checks = [
        ("OpenAI API",   check_openai(settings)),
        ("Neon Postgres", check_postgres(settings)),
        ("Upstash Redis", check_redis(settings)),
        ("Langfuse Cloud", check_langfuse(settings)),
        ("Jina AI",       check_jina(settings)),
    ]

    print("\n── API Connectivity Check ─────────────────────────────────────")
    for name, coro in checks:
        try:
            result = await coro
            print(f"  ✅  {name:<20} {result}")
        except Exception as e:
            print(f"  ❌  {name:<20} FAILED — {e}")

    print("\n── Postgres DNS Resolution ────────────────────────────────────")
    try:
        host, resolved = check_postgres_ipv4(settings)
        print(f"  Host: {host}")
        for family, addr in resolved:
            icon = "✅" if family == "IPv4" else "⚠️ "
            print(f"  {icon}  {family}: {addr}")
        if all(f == "IPv6" for f, _ in resolved):
            print("\n  ⚠️  Only IPv6 addresses found — may cause deployment issues.")
            print("     Fix: switch to Neon pooler URL (see output below).")
            pooler_host = host.replace(host.split(".")[0], host.split(".")[0] + "-pooler")
            pooler_url = settings.postgres_database_url.replace(host, pooler_host).replace(":5432", ":6432")
            print(f"\n  Pooler URL (IPv4-only):\n  {pooler_url}")
    except Exception as e:
        print(f"  ❌  DNS check failed — {e}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
