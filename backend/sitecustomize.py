# sitecustomize.py
# Automatically loaded by Python's site module on interpreter startup.
# Installs Air Point Test Guard when AIRPOINT_ENABLE_TEST_GUARD=1.

import os

if os.environ.get("AIRPOINT_ENABLE_TEST_GUARD", "").strip().lower() in ("1", "true", "yes"):
    try:
        from test_guard import install_test_guard
        install_test_guard()
    except Exception as e:
        import sys
        sys.stderr.write(f"Warning: Failed to install test guard: {e}\n")
