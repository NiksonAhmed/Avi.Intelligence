"""Command-line SharePoint connection check.

    uv run python -m app.check_sharepoint

Reads settings from .env, runs the same checks as Administration > Connectors and prints the
library's columns so SHAREPOINT_SOP_FIELD_MAP can be configured. Prints no secrets.
"""

from __future__ import annotations

import asyncio
import sys

import truststore

from app.connectors.sharepoint import build_sop_connector
from app.core.config import get_settings


async def main() -> int:
    settings = get_settings()
    if settings.use_system_trust_store:
        truststore.inject_into_ssl()  # corporate TLS inspection: trust the Windows certificate store
    connector = build_sop_connector(settings)
    info = connector.info()
    print(f"Mode:    {info.mode}" + (f"  ({info.mock_reason})" if info.mock_reason else ""))
    print(f"Site:    {info.site_url or '-'}")
    print(f"Library: {info.library}")
    print(f"Folder:  {info.folder or '(whole library)'}\n")

    check = await connector.test_connection()
    for step in check.steps:
        mark = "PASS" if step.ok else "FAIL"
        print(f"[{mark}] {step.label}" + (f": {step.detail}" if step.detail else ""))

    if check.columns:
        print("\nLibrary columns (internal name -> display name):")
        for col in sorted(check.columns, key=lambda c: c.display_name.lower()):
            print(f"  {col.name:<40} {col.display_name}  [{col.type}]")

    if info.mode == "live" and check.ok:
        result = await connector.list_sops()
        print(f"\nFirst SOPs found ({len(result.documents)} total):")
        for doc in result.documents[:10]:
            number = doc.sop_number or "-"
            print(f"  {number:<12} {doc.status.value:<11} v{doc.version or '?':<6} {doc.title}")
    return 0 if check.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
