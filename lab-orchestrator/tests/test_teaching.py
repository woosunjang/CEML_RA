"""Phase 2 Teaching Agent tests on M2 Mac Mini."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import json

API = "http://localhost:8000"
results = []

print("=== Phase 2: Teaching Agent Tests ===\n")

# Test 1: 강의안 생성
print("1. 강의안 생성...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "NASICON 고체전해질을 대학원생 대상 90분 강의 슬라이드 5장으로 구성해줘"
}, timeout=120)
d = r.json()
steps = d.get("execution_steps", [])
agents_used = [s["agent"] for s in steps]
has_slides = "Slide" in d["content"] or "슬라이드" in d["content"] or "###" in d["content"]
submode = d.get("metadata", {}).get("submode") if "teaching" in agents_used else None
passed = "teaching" in agents_used and len(d["content"]) > 200 and has_slides
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, {len(d['content'])} chars, slides={'yes' if has_slides else 'no'}")

# Test 2: 퀴즈 생성
print("2. 퀴즈 생성...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "고체전해질 기초 퀴즈 3문제 만들어줘"
}, timeout=120)
d = r.json()
steps = d.get("execution_steps", [])
agents_used = [s["agent"] for s in steps]
has_quiz = "문제" in d["content"] or "정답" in d["content"]
has_artifacts = len(d.get("metadata", {}).get("artifacts", [])) > 0 if "metadata" in d else False
passed = "teaching" in agents_used and has_quiz and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, {len(d['content'])} chars, quiz={'yes' if has_quiz else 'no'}")

# Test 3: 노트북 생성
print("3. 노트북 생성...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "이온전도도 계산 실습 Jupyter 노트북 만들어줘"
}, timeout=120)
d = r.json()
steps = d.get("execution_steps", [])
agents_used = [s["agent"] for s in steps]
has_notebook = "노트북" in d["content"] or "notebook" in d["content"].lower() or "ipynb" in d["content"]
passed = "teaching" in agents_used and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, {len(d['content'])} chars, notebook={'yes' if has_notebook else 'no'}")

# Test 4: Literature → Teaching 체이닝
print("4. Literature→Teaching 체이닝...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "NASICON 최신 논문 분석하고 세미나 강의안 만들어줘"
}, timeout=180)
d = r.json()
steps = d.get("execution_steps", [])
agents_used = [s["agent"] for s in steps]
is_multi = d.get("metadata", {}).get("is_multi_agent", False)
passed = "literature" in agents_used and "teaching" in agents_used and len(d["content"]) > 200
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents_used}, multi={is_multi}, {len(d['content'])} chars")

total = sum(results)
print(f"\n=== Result: {total}/4 passed ===")
