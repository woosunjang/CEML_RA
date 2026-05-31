"""Quick test: in-process orchestrator (single process, no agent servers)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

API = "http://localhost:8000"

# Health
r = httpx.get(f"{API}/health", timeout=5)
print(f"Health: {r.json()}")

# Agents
r = httpx.get(f"{API}/agents", timeout=5)
agents = r.json()["agents"]
for a in agents:
    print(f"  {a['icon']} {a['name']}: online={a['online']}")

# Chat
r = httpx.post(f"{API}/chat", json={"message": "NASICON 관련 최신 연구 요약"}, timeout=60)
d = r.json()
print(f"\nChat: agent={d['agent_name']}, {len(d['content'])} chars")
steps = d.get("execution_steps", [])
print(f"Steps: {[(s['agent'], s['status']) for s in steps]}")
print(f"Preview: {d['content'][:150]}...")
print("\nDone.")
