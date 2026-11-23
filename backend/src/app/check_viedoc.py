"""Step 0: find out what the Viedoc API offers (read-only, from the command line).

    uv run python -m app.check_viedoc                       # sign in, list the endpoints
    uv run python -m app.check_viedoc --connection sandbox  # pick a connection when there are several
    uv run python -m app.check_viedoc --try "/some/path?x=1" # shape of one GET response (names only)
    uv run python -m app.check_viedoc --save-spec C:\\temp\\viedoc-api.json
    uv run python -m app.check_viedoc --trial-export         # one export: structure only, then deleted

Connections come from `.env`: VIEDOC_CONNECTIONS__<NAME>__API_URL, __CLIENT_ID, __CLIENT_SECRET, optionally
__TOKEN_URL, __SCOPE and __ENVIRONMENT (sandbox, the default, or live). Live connections are refused unless
VIEDOC_ALLOW_LIVE=true.

Never prints secrets, tokens or data values: only endpoint names, field names, types and counts. The saved
API description is Viedoc's documentation; keep it out of the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import truststore

from app.connectors.viedoc.client import (
    ViedocClient,
    ViedocError,
    describe_columns,
    describe_export_file,
    describe_shape,
    list_endpoints,
)
from app.core.config import Settings, get_settings

# What Data Management needs from an export; filters (sites, forms, items) narrow it further later.
TRIAL_EXPORT = {
    "outputFormat": "CSV",
    "includeQueries": True,
    "includeQueryHistory": True,
    "includePendingForms": True,
    "includeEditStatus": True,
}


def _pick(settings: Settings, name: str | None) -> tuple[str, ViedocClient] | str:
    connections = settings.viedoc_connections
    if not connections:
        return (
            "No Viedoc connection in .env. Add VIEDOC_CONNECTIONS__SANDBOX__API_URL, __CLIENT_ID and "
            "__CLIENT_SECRET (from the API client you created in Viedoc)."
        )
    if name is None:
        if len(connections) > 1:
            return f"Several connections ({', '.join(sorted(connections))}): choose one with --connection."
        name = next(iter(connections))
    key = name.lower()
    if key not in connections:
        return f"No connection called {name!r} (have: {', '.join(sorted(connections))})."
    return key, ViedocClient(connections[key], allow_live=settings.viedoc_allow_live)


async def run(args: argparse.Namespace, settings: Settings) -> int:
    try:
        picked = _pick(settings, args.connection)
        if isinstance(picked, str):
            print(picked)
            return 1
        name, client = picked
        conn = client.connection
        print(f"Connection: {name} ({conn.environment.upper()})  API: {client.api_url}")

        await client.sign_in()
        print(
            "Signed in: yes"
            + (f" · token valid {client.token_expires_in}s" if client.token_expires_in else "")
            + (f" · scopes: {', '.join(client.granted_scopes)}" if client.granted_scopes else "")
        )

        if getattr(args, "trial_export", False):
            print("\nTrial export (CSV with queries, query history, pending forms and edit status)...")
            content = await client.run_export(TRIAL_EXPORT)
            print("Export ready, read in memory, and deleted from Viedoc's server.")
            print("Contents (file names, column names and row counts only):")
            for line in describe_export_file(content, "export"):
                print("  " + line)
            for spec in getattr(args, "values", None) or []:
                suffix, _, cols = spec.partition(":")
                print(f"\nVocabulary of {suffix} (few distinct values shown; free text never):")
                for line in describe_columns(
                    content, suffix, [c.strip() for c in cols.split(",") if c.strip()]
                ):
                    print("  " + line)
            return 0

        if args.try_path:
            status, body = await client.get(args.try_path)
            print(f"\nGET {args.try_path} -> HTTP {status}")
            if body is None:
                print("(no JSON body)")
            else:
                print("Response structure (names, types and counts only):")
                for line in describe_shape(body):
                    print("  " + line)
            return 0 if status == 200 else 3

        found = await client.find_spec()
        if found is None:
            print(
                "\nNo Swagger/OpenAPI description at the usual addresses. Open the Swagger UI from Viedoc's "
                "API documentation, then try endpoints one at a time with --try."
            )
            return 0
        url, spec = found
        info = spec.get("info", {})
        print(f"\nAPI description: {url}")
        print(f"Title: {info.get('title', '-')}  Version: {info.get('version', '-')}")
        rows = list_endpoints(spec)
        print(f"{len(rows)} endpoints ({sum(r['method'] == 'GET' for r in rows)} read-only GET):")
        for r in rows:
            mark = "  " if r["method"] == "GET" else "! "  # avi.intelligence only ever uses GET
            areas = f"  [{r['areas']}]" if r["areas"] else ""
            print(f"{mark}{r['method']:6s} {r['path']}  {r['summary']}{areas}")
        if args.save_spec:
            target = Path(args.save_spec)
            await asyncio.to_thread(target.write_text, json.dumps(spec, indent=2), encoding="utf-8")
            print(f"\nSaved the API description to {target} (keep it out of the repository).")
        return 0
    except ViedocError as exc:
        print(f"FAILED: {exc}")
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Viedoc API discovery (Step 0).")
    parser.add_argument("--connection", help="Connection name from .env (e.g. sandbox).")
    parser.add_argument("--try", dest="try_path", help="One GET path to describe (names only).")
    parser.add_argument("--save-spec", help="Save the API description (outside the repository).")
    parser.add_argument(
        "--trial-export", action="store_true", help="Run one export, show its structure only, delete it."
    )
    parser.add_argument(
        "--values",
        action="append",
        help="With --trial-export: FILE_SUFFIX:col1,col2 to list each column's few distinct values.",
    )
    args = parser.parse_args()
    # Column names can contain characters the Windows console cannot show; never crash on them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    settings = get_settings()
    if settings.use_system_trust_store:
        truststore.inject_into_ssl()
    return asyncio.run(run(args, settings))


if __name__ == "__main__":
    sys.exit(main())
