"""Configuration is loaded once per service, never printed."""
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
# The desktop process reloads its project .env after a restart. MCP children
# receive an explicit, already-resolved environment from the parent and must
# not overwrite it with the file again.
load_dotenv(ROOT / '.env', override=os.getenv('AUDIT_MCP_CHILD') != '1')

@dataclass
class Settings:
    model: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'))
    api_key: str = field(default_factory=lambda: os.getenv('GEMINI_API_KEY', ''))
    extraction_mode: str = field(default_factory=lambda: os.getenv('INVOICE_EXTRACTION_MODE', 'gemini'))
    state_path: str = field(default_factory=lambda: os.getenv('CHECKPOINT_PATH', str(ROOT / 'data/audit_state.sqlite')))
    db_mode: str = field(default_factory=lambda: os.getenv('DB_MODE', 'sqlserver'))
    db_connection: str = field(default_factory=lambda: os.getenv('DB_CONNECTION_STRING', ''))
    demo_db: str = field(default_factory=lambda: os.getenv('DEMO_DB_PATH', str(ROOT / 'data/demo.sqlite')))
    web_mode: str = field(default_factory=lambda: os.getenv('WEB_RISK_MODE', 'live'))
    policy_mode: str = field(default_factory=lambda: os.getenv('POLICY_MODE', 'chroma'))
    timeout: float = field(default_factory=lambda: float(os.getenv('AUDIT_TIMEOUT_SECONDS','60')))
    retries: int = field(default_factory=lambda: int(os.getenv('AUDIT_RETRIES','2')))
    max_iterations: int = field(default_factory=lambda: int(os.getenv('AUDIT_MAX_ITERATIONS','3')))
    max_tool_calls: int = field(default_factory=lambda: int(os.getenv('AUDIT_MAX_TOOL_CALLS','6')))

    def __post_init__(self):
        if not 1 <= self.timeout <= 120 or not 0 <= self.retries <= 3 or not 1 <= self.max_iterations <= 5 or not 1 <= self.max_tool_calls <= 10:
            raise ValueError('Audit execution limits outside supported bounds')
        if self.extraction_mode not in ('gemini', 'demo_deterministic'):
            raise ValueError('INVOICE_EXTRACTION_MODE must be gemini or demo_deterministic')
