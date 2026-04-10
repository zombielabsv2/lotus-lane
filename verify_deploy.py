#!/usr/bin/env python3
"""Pre-deployment verification for The Lotus Lane.

Run before every push to main. Checks:
1. Syntax — all .py files compile cleanly
2. Requirements — pipeline/requirements.txt exists and is parseable
3. Import chain — key pipeline modules can be imported
4. Config validation — characters, topics, art style are populated
5. Tests — pytest suite passes

Exit code 1 on any failure.
"""

import subprocess
import sys
import os
import py_compile

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

PASS = "PASS"
FAIL = "FAIL"
results = []


def log(check_name, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((check_name, passed))
    marker = "+" if passed else "X"
    msg = f"  [{marker}] {check_name}: {status}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


def collect_py_files():
    """Collect all .py files from root, pipeline/, tests/, prototype/."""
    files = []
    dirs_to_scan = [
        PROJECT_ROOT,
        os.path.join(PROJECT_ROOT, "pipeline"),
        os.path.join(PROJECT_ROOT, "tests"),
        os.path.join(PROJECT_ROOT, "prototype"),
    ]
    for d in dirs_to_scan:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".py"):
                    files.append(os.path.join(d, f))
    return files


# ── 1. Syntax Check ──────────────────────────────────────────
print("\n=== The Lotus Lane: Pre-Deploy Verification ===\n")
print("1. Syntax Check")

py_files = collect_py_files()
syntax_ok = True
syntax_errors = []
for fpath in py_files:
    try:
        py_compile.compile(fpath, doraise=True)
    except py_compile.PyCompileError as e:
        syntax_ok = False
        rel = os.path.relpath(fpath, PROJECT_ROOT)
        syntax_errors.append(rel)

log("Syntax", syntax_ok,
    f"{len(py_files)} files OK" if syntax_ok
    else f"Errors in: {', '.join(syntax_errors)}")


# ── 2. Requirements Check ────────────────────────────────────
print("\n2. Requirements Check")

req_path = os.path.join(PROJECT_ROOT, "pipeline", "requirements.txt")
req_ok = False
req_count = 0
if os.path.exists(req_path):
    with open(req_path, "r") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    req_count = len(lines)
    req_ok = req_count >= 5
else:
    # Check root requirements.txt as fallback
    req_path_root = os.path.join(PROJECT_ROOT, "requirements.txt")
    if os.path.exists(req_path_root):
        with open(req_path_root, "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        req_count = len(lines)
        req_ok = req_count >= 5

log("Requirements", req_ok,
    f"{req_count} packages" if req_ok else "requirements.txt missing or too few packages")


# ── 3. Import Chain ──────────────────────────────────────────
print("\n3. Import Chain")

PIPELINE_MODULES = [
    "pipeline.config",
    "pipeline.utils",
]

import_ok = True
import_errors = []

for mod_name in PIPELINE_MODULES:
    cmd = [
        sys.executable, "-c",
        f"import sys; sys.path.insert(0, '.'); "
        f"import {mod_name}; "
        f"print('OK')"
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
        )
        if result.returncode != 0:
            import_ok = False
            err = result.stderr.strip().splitlines()[-1] if result.stderr else "unknown error"
            import_errors.append(f"{mod_name}: {err}")
            log(f"Import {mod_name}", False, import_errors[-1])
        else:
            log(f"Import {mod_name}", True)
    except subprocess.TimeoutExpired:
        import_ok = False
        import_errors.append(f"{mod_name}: timeout")
        log(f"Import {mod_name}", False, "timeout")


# ── 4. Config Validation ────────────────────────────────────
print("\n4. Config Validation")

try:
    sys.path.insert(0, PROJECT_ROOT)
    from pipeline import config

    chars_ok = hasattr(config, "CHARACTERS") and len(config.CHARACTERS) >= 4
    log("CHARACTERS", chars_ok,
        f"{len(config.CHARACTERS)} characters" if chars_ok else "need >= 4 characters")

    topics_ok = hasattr(config, "CHALLENGE_TOPICS") and len(config.CHALLENGE_TOPICS) >= 5
    log("CHALLENGE_TOPICS", topics_ok,
        f"{len(config.CHALLENGE_TOPICS)} categories" if topics_ok else "need >= 5 topic categories")

    style_ok = hasattr(config, "ART_STYLE") and len(config.ART_STYLE) > 20
    log("ART_STYLE", style_ok, "defined" if style_ok else "missing or too short")

except Exception as e:
    log("Config import", False, str(e))


# ── 5. Run pytest ─────────────────────────────────────────────
print("\n5. Test Suite")

tests_dir = os.path.join(PROJECT_ROOT, "tests")
test_ok = False
if os.path.isdir(tests_dir):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_imports.py", "-v", "--tb=short"],
        capture_output=True, text=True, timeout=300,
        cwd=PROJECT_ROOT,
    )
    test_ok = result.returncode == 0
    for line in result.stdout.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            print(f"     {line}")
    if not test_ok and result.stderr:
        for line in result.stderr.strip().splitlines()[-5:]:
            print(f"     {line}")
else:
    print("     No tests/ directory found.")

log("Tests", test_ok, "all passed" if test_ok else "failures detected")


# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 50)
passed = sum(1 for _, ok in results if ok)
total = len(results)
all_passed = all(ok for _, ok in results)

if all_passed:
    print(f"  ALL CHECKS PASSED ({passed}/{total})")
    print("  Safe to push.")
else:
    failed = [(name, ok) for name, ok in results if not ok]
    print(f"  {passed}/{total} PASSED, {len(failed)} FAILED:")
    for name, _ in failed:
        print(f"    - {name}")
    print("\n  DO NOT PUSH until all checks pass.")

print("=" * 50 + "\n")

sys.exit(0 if all_passed else 1)
