"""Legacy tutorial entry point for current API acceptance tests."""
if __name__ == '__main__':
    import subprocess
    import sys
    raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','tests/test_api_ui.py']))
