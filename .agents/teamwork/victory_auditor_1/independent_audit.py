import os
import hashlib
from pathlib import Path

skills = [
    ('agency-sre-site-reliability-engineer', r'C:\Users\AmirM\.gemini\config\skills\agency-sre-site-reliability-engineer'),
    ('agency-devops-automator', r'C:\Users\AmirM\.gemini\config\skills\agency-devops-automator'),
    ('agency-incident-response-commander', r'C:\Users\AmirM\.gemini\config\skills\agency-incident-response-commander'),
    ('agency-autonomous-optimization-architect', r'C:\Users\AmirM\.gemini\config\skills\agency-autonomous-optimization-architect'),
    ('agency-secrets-credential-hygiene-engineer', r'C:\Users\AmirM\.gemini\config\skills\agency-secrets-credential-hygiene-engineer'),
    ('agency-cloud-security-architect', r'C:\Users\AmirM\.gemini\config\skills\agency-cloud-security-architect'),
    ('agency-finops-engineer', r'C:\Users\AmirM\.gemini\config\skills\agency-finops-engineer'),
    ('agency-api-tester', r'C:\Users\AmirM\.gemini\config\skills\agency-api-tester'),
    ('agency-performance-benchmarker', r'C:\Users\AmirM\.gemini\config\skills\agency-performance-benchmarker'),
    ('agency-realtime-collaboration-engineer', r'C:\Users\AmirM\.gemini\config\skills\agency-realtime-collaboration-engineer'),
    ('docker-containerization', r'c:\Users\AmirM\Documents\Agentic trading\repos\skills-for-antigravity\skills\docker-containerization'),
    ('observability-sre', r'c:\Users\AmirM\Documents\Agentic trading\repos\skills-for-antigravity\skills\observability-sre')
]

root = Path(r'c:\Users\AmirM\Documents\Agentic trading')
catalogs = [
    root / '.agents' / 'skills',
    root / '.agent' / 'skills'
]

total_files_checked = 0
all_matched = True

print("=== INDEPENDENT BIT-FOR-BIT CRYPTOGRAPHIC AUDIT ===")

for sk_name, src_dir_str in skills:
    src_dir = Path(src_dir_str)
    if not src_dir.is_dir():
        print(f"[FAIL] Source directory missing: {src_dir}")
        all_matched = False
        continue

    src_files = {}
    for p in src_dir.rglob('*'):
        if p.is_file():
            rel = p.relative_to(src_dir)
            src_files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()

    for cat in catalogs:
        dst_dir = cat / sk_name
        if not dst_dir.is_dir():
            print(f"[FAIL] Destination directory missing: {dst_dir}")
            all_matched = False
            continue

        dst_files = {}
        for p in dst_dir.rglob('*'):
            if p.is_file():
                rel = p.relative_to(dst_dir)
                dst_files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()

        if set(src_files.keys()) != set(dst_files.keys()):
            print(f"[FAIL] File set mismatch in {dst_dir}: {set(src_files.keys()) ^ set(dst_files.keys())}")
            all_matched = False

        for rel, h in src_files.items():
            total_files_checked += 1
            if rel in dst_files:
                if dst_files[rel] != h:
                    print(f"[FAIL] Hash mismatch in {dst_dir / rel}: target {dst_files[rel]} != source {h}")
                    all_matched = False
                else:
                    print(f"[OK] {cat.name}/{sk_name}/{rel}: {h[:12]}... (MATCH)")
            else:
                print(f"[FAIL] Missing file in {dst_dir}: {rel}")
                all_matched = False

print(f"\nTotal files independently verified: {total_files_checked}")
if all_matched:
    print("VERDICT: ALL 12 SKILLS EXACT BIT-FOR-BIT MATCH AGAINST SOURCES")
else:
    print("VERDICT: INTEGRITY VIOLATION DETECTED")
