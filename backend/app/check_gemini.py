"""Safe local Gemini diagnostic; prints configuration state, never the API key."""
import asyncio
from dataclasses import replace

from backend.app.config import Settings
from backend.app.gemini import Gemini


async def main():
    # One extraction request is enough to diagnose the credential/model path.
    # Disable application retries here so an exhausted free tier is not probed
    # repeatedly by a health-check command.
    settings=replace(Settings(), retries=0)
    if not settings.api_key:
        print('Gemini check failed: GEMINI_API_KEY is empty in .env')
        return 1
    model=Gemini(settings)
    try:
        invoice=await model.extract('''INVOICE ID: INV-GEMINI-CHECK
PO NUMBER: PO-1001
Vendor: Acme IT Solutions
Total Amount Billed: USD 1,200.00
Description: Connection check''')
        print('Gemini connection: OK')
        print('Model:', settings.model)
        print('Invoice extraction: OK')
        print('Run a single audit in the UI next to verify the explanation and approval path.')
        return 0
    except Exception as exc:
        print('Gemini check failed:', type(exc).__name__)
        # Provider errors contain useful status/quota/model diagnostics. Do not
        # print settings, prompts, invoice data, or the configured API key.
        detail=' '.join(str(exc).split())[:500]
        if detail:
            print('Provider detail:', detail)
        return 1
    finally:
        await model.close()


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
