"""Phase 3: Writing + Presentation Agent tests on M2 Mac Mini."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import json

API = "http://localhost:8000"
results = []

print("=== Phase 3: Writing + Presentation Tests ===\n")

# Test 1: 제안서 생성
print("1. 제안서 생성 (proposal)...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "NASICON 기반 고체전해질 연구 제안서 작성해줘"
}, timeout=120)
d = r.json()
agents_used = [s["agent"] for s in d.get("execution_steps", [])]
has_sections = any(kw in d["content"] for kw in ["연구 배경", "연구 목표", "Background", "Objective"])
has_save = "저장 완료" in d["content"]
passed = "writing" in agents_used and has_sections and len(d["content"]) > 300
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, {len(d['content'])} chars, sections={'yes' if has_sections else 'no'}, saved={'yes' if has_save else 'no'}")

# Test 2: 초록 생성
print("2. 초록 생성 (abstract)...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "이온전도도 향상 연구의 초록을 작성해줘"
}, timeout=120)
d = r.json()
agents_used = [s["agent"] for s in d.get("execution_steps", [])]
has_abstract = any(kw in d["content"] for kw in ["배경", "목적", "방법", "결론", "키워드"])
passed = "writing" in agents_used and has_abstract and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, {len(d['content'])} chars, abstract={'yes' if has_abstract else 'no'}")

# Test 3: 리뷰 응답
print("3. 리뷰 응답 (review_response)...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "리뷰어가 실험 재현성이 부족하다고 했는데 리뷰 응답서 작성해줘"
}, timeout=120)
d = r.json()
agents_used = [s["agent"] for s in d.get("execution_steps", [])]
has_response = any(kw in d["content"] for kw in ["응답", "수정", "Reviewer"])
passed = "writing" in agents_used and has_response and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, {len(d['content'])} chars, response={'yes' if has_response else 'no'}")

# Test 4: PPTX 생성
print("4. PPTX 생성 (presentation)...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "고체전해질 연구 발표 자료 5장 PPT 만들어줘"
}, timeout=120)
d = r.json()
agents_used = [s["agent"] for s in d.get("execution_steps", [])]
has_pptx = "PowerPoint" in d["content"] or "pptx" in d["content"].lower() or "슬라이드" in d["content"]
has_save = "저장 위치" in d["content"]
passed = "presentation" in agents_used and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, {len(d['content'])} chars, pptx={'yes' if has_pptx else 'no'}, saved={'yes' if has_save else 'no'}")

# Test 5: Literature → Writing 체이닝
print("5. Literature→Writing 체이닝...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "NASICON 최신 동향 분석 후 제안서 작성해줘"
}, timeout=180)
d = r.json()
agents_used = [s["agent"] for s in d.get("execution_steps", [])]
is_multi = d.get("metadata", {}).get("is_multi_agent", False)
passed = "literature" in agents_used and "writing" in agents_used and len(d["content"]) > 200
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, multi={is_multi}, {len(d['content'])} chars")

# Test 6: Literature → Presentation 체이닝
print("6. Literature→Presentation 체이닝...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "최신 논문 분석하고 세미나 발표 자료 만들어줘"
}, timeout=180)
d = r.json()
agents_used = [s["agent"] for s in d.get("execution_steps", [])]
is_multi = d.get("metadata", {}).get("is_multi_agent", False)
passed = "literature" in agents_used and "presentation" in agents_used and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, multi={is_multi}, {len(d['content'])} chars")

total = sum(results)
print(f"\n=== Result: {total}/6 passed ===")
