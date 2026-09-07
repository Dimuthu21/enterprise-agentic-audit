"""Legacy tutorial entry point for real stdio MCP tests, using temporary databases."""
if __name__ == '__main__':
    import subprocess
    import sys
    raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','tests/test_mcp.py']))
