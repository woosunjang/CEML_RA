"""Phase 4 integration tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import json

API = "http://localhost:8000"
results = []

print("=== Phase 4 Tests ===\n")

# Test 1: New API endpoints
print("1. New API endpoints...", flush=True)
ws = httpx.get(f"{API}/workspaces", timeout=10).json()
proj = httpx.get(f"{API}/projects", timeout=10).json()
dl = httpx.get(f"{API}/deadlines", timeout=10).json()
ws_ok = "workspaces" in ws and len(ws["workspaces"]) >= 3
proj_ok = "projects" in proj
dl_ok = "deadlines" in dl
passed = ws_ok and proj_ok and dl_ok
results.append(passed)
ws_names = [w["key"] for w in ws.get("workspaces", [])]
print(f"   [{'PASS' if passed else 'FAIL'}] workspaces={ws_names}, projects={len(proj.get('projects',[]))}")

# Test 2: Workspace context injection
print("2. Workspace context (ontology)...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "이 프로젝트 배경 설명해줘",
    "workspace": "ontology"
}, timeout=60)
d = r.json()
has_ontology = "온톨로지" in d["content"] or "ontology" in d["content"].lower()
passed = d["content"] and len(d["content"]) > 50
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] len={len(d['content'])}, ontology_mention={has_ontology}")

# Test 3: Project Agent — milestone submode
print("3. Project milestone...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "프로젝트 마일스톤 현황 정리해줘. 문헌조사 완료, 실험설계 진행중이야."
}, timeout=60)
d = r.json()
agents = [s["agent"] for s in d.get("execution_steps", [])]
has_milestone = "마일스톤" in d["content"] or "진행" in d["content"]
passed = "project" in agents and has_milestone
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents}")

# Test 4: Project Agent — deadline submode
print("4. Project deadline...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "KCI 논문 마감이 8월 15일이야. 준비 일정 세워줘."
}, timeout=60)
d = r.json()
agents = [s["agent"] for s in d.get("execution_steps", [])]
has_deadline = "마감" in d["content"] or "D-" in d["content"]
passed = "project" in agents and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents}, deadline={has_deadline}")

# Test 5: Project Agent — meeting submode
print("5. Project meeting...", flush=True)
r = httpx.post(f"{API}/chat", json={
    "message": "오늘 회의 내용 정리해줘: 김교수님이 NASICON 도핑 실험 결과 검토 요청함. 다음주까지 XRD 데이터 분석 완료 필요. 이박사가 DFT 시뮬레이션 세팅 담당."
}, timeout=60)
d = r.json()
agents = [s["agent"] for s in d.get("execution_steps", [])]
has_action = "액션" in d["content"] or "담당" in d["content"]
passed = "project" in agents and len(d["content"]) > 100
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] agents={agents}, action_items={has_action}")

# Test 6: Session persistence (conversation_id reuse)
print("6. Session persistence...", flush=True)
conv_id = d.get("conversation_id", "")
if conv_id:
    sessions = httpx.get(f"{API}/sessions", timeout=10).json()
    has_session = conv_id in sessions.get("sessions", [])
    passed = has_session
else:
    passed = False
results.append(passed)
print(f"   [{'PASS' if passed else 'FAIL'}] conv_id={conv_id[:12]}..., persisted={passed}")

# Test 7: File saving
print("7. File saving...", flush=True)
import subprocess
check = subprocess.run(
    ["ssh", "mersoom@Mersoomui-Macmini.local",
     "ls -la ~/Dropbox/Dev/CEML_RA/generated/project/ 2>/dev/null | tail -3"],
    capture_output=True, text=True, timeout=10
)
has_files = ".md" in check.stdout
results.append(has_files)
print(f"   [{'PASS' if has_files else 'FAIL'}] files: {check.stdout.strip()[-80:]}")

total = sum(results)
print(f"\n=== Result: {total}/{len(results)} passed ===")
