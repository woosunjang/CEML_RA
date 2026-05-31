"""Presentation Agent enhancement tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import json

API = "http://localhost:8000"
results = []

print("=== Presentation Agent Enhancement Tests ===\n")

# Test 1: 기본 (이미지 없이, 기본 테마)
print("1. 기본 PPTX (dark_academic)...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "고체전해질 연구 발표 5장 PPT 만들어줘"
}, timeout=120)
d = r.json()
agents = [s["agent"] for s in d.get("execution_steps", [])]
has_pptx = "PowerPoint" in d["content"] or "pptx" in d["content"].lower()
has_save = "저장 위치" in d["content"]
has_theme = "dark_academic" in d["content"]
passed = "presentation" in agents and has_pptx and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents}, pptx={has_pptx}, saved={has_save}, theme={has_theme}")

# Test 2: 밝은 테마
print("2. 밝은 테마 PPTX...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "밝은 테마로 이온전도 발표 3장 PPT 만들어줘"
}, timeout=120)
d = r.json()
agents = [s["agent"] for s in d.get("execution_steps", [])]
has_light = "light" in d["content"].lower() or "밝은" in d["content"]
passed = "presentation" in agents and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents}, light_theme={has_light}")

# Test 3: JSON structured output 안정성
print("3. JSON structured output...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "NASICON 발표 자료 7장 PPT"
}, timeout=120)
d = r.json()
agents = [s["agent"] for s in d.get("execution_steps", [])]
# Check for successful parsing (has slides preview)
has_slides = "Slide" in d["content"]
failed = "파싱 실패" in d["content"] or d["content"].startswith("{")
passed = "presentation" in agents and has_slides and not failed
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents}, slides_parsed={has_slides}, json_failed={failed}")

total = sum(results)
print(f"\n=== Result: {total}/3 passed ===")
