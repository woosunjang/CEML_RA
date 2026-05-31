"""E2E test script for M2 Mac Mini validation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

API = "http://localhost:8000"

print("=== E2E Tests on M2 Mac Mini ===\n")

results = []

# Test a: 단일 에이전트
r = httpx.post(f"{API}/chat", json={"message": "NASICON 논문 분석해줘"}, timeout=60)
d = r.json()
steps = d.get("execution_steps", [])
passed = d["agent_name"] == "literature" and len(d["content"]) > 100
results.append(passed)
mark = "PASS" if passed else "FAIL"
print(f"a. 단일 에이전트: [{mark}] agent={d['agent_name']}, {len(d['content'])} chars")

# Test b: Multi-turn
cid = d["conversation_id"]
r2 = httpx.post(f"{API}/chat", json={"message": "그 중 가장 핵심적인 내용 요약해줘", "conversation_id": cid}, timeout=60)
d2 = r2.json()
passed_b = d2["conversation_id"] == cid and len(d2["content"]) > 50
results.append(passed_b)
mark = "PASS" if passed_b else "FAIL"
print(f"b. Multi-turn:     [{mark}] conv_match={d2['conversation_id']==cid}, {len(d2['content'])} chars")

# Test c: 에이전트 전환
r3 = httpx.post(f"{API}/chat", json={"message": "NASICON 고체전해질 제안서 배경 문단 작성해줘"}, timeout=120)
d3 = r3.json()
steps3 = d3.get("execution_steps", [])
agents_used = [s["agent"] for s in steps3]
passed_c = "writing" in agents_used and len(d3["content"]) > 100
results.append(passed_c)
mark = "PASS" if passed_c else "FAIL"
print(f"c. 에이전트 전환:  [{mark}] agents={agents_used}, {len(d3['content'])} chars")

# Test d: 멀티 에이전트
r4 = httpx.post(f"{API}/chat", json={"message": "NASICON 동향 정리하고 강의안 만들어줘"}, timeout=120)
d4 = r4.json()
steps4 = d4.get("execution_steps", [])
agents4 = [s["agent"] for s in steps4]
passed_d = len(steps4) >= 2 and all(s["status"] == "completed" for s in steps4)
results.append(passed_d)
mark = "PASS" if passed_d else "FAIL"
print(f"d. 멀티 에이전트:  [{mark}] agents={agents4}, multi={d4['metadata'].get('is_multi_agent')}")

# Test e: Scout 연동
from integrations.scout_reader import ScoutReader
reader = ScoutReader()
stats = reader.get_stats() if reader.available else {}
passed_e = reader.available and stats.get("total", 0) > 0
results.append(passed_e)
mark = "PASS" if passed_e else "FAIL"
print(f"e. Scout 연동:     [{mark}] total={stats.get('total',0)}, avg={stats.get('avg_score',0):.1f}")

total = sum(results)
print(f"\n=== Result: {total}/5 passed ===")
