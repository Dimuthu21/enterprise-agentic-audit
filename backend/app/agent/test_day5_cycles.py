"""Legacy tutorial entry point; meaningful replacement tests use the current workflow."""
if __name__ == '__main__':
    import subprocess
    import sys
    raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','tests/test_workflow.py']))
