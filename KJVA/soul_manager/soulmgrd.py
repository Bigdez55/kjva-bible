"""soul_manager/soulmgrd.py — SoulManager daemon server at port 18610.

Binds :18610 and dispatches put/get/list_keys/delete/agent_stats JSON-RPC
calls to SoulManager.

JSON-RPC wire format (newline-terminated, max 65536 bytes per request):
  Request:  {"method": "<name>", "params": {...}}
  Response: {"result": <value>} | {"error": "<message>"}

Supported methods and params:
  put         {"agent": str, "bucket": str, "sub_path": str, "value": <any>}
  get         {"agent": str, "bucket": str, "sub_path": str}
  list_keys   {"agent": str, "bucket": str, "prefix": str}   # prefix optional
  delete      {"agent": str, "bucket": str, "sub_path": str}
  agent_stats {"agent": str}

Start with:
  TOKENLESS_SOUL_ALLOW_PLAINTEXT=1 python3 soulmgrd.py   # dev/no-crypto env
  python3 soulmgrd.py                                      # production (needs AES backend)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# Allow direct execution: ensure the parent directory (soul_manager/) is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Also insert the package parent so relative imports inside soul_manager work
_PKG_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from soul_manager import SoulManager  # noqa: E402

logger = logging.getLogger("tokenless.soulmgrd")

SOUL_MGR_HOST = os.environ.get("SOULMGRD_HOST", "127.0.0.1")
SOUL_MGR_PORT = int(os.environ.get("SOULMGRD_PORT", "18610"))

# Module-level singleton — shared across all connections in this process.
_soul_manager: SoulManager | None = None


def _get_manager() -> SoulManager:
    """Return the process-level SoulManager singleton, creating it on first call."""
    global _soul_manager
    if _soul_manager is None:
        _soul_manager = SoulManager()
        logger.info("SoulManager singleton created (soulmgrd)")
    return _soul_manager


async def _dispatch(req: dict) -> object:
    """Dispatch a JSON-RPC request dict to the appropriate SoulManager method.

    Returns the result value (to be serialised as {"result": ...}).
    Raises ValueError for unknown/malformed requests.
    """
    method = req.get("method", "")
    params: dict = req.get("params", {})
    mgr = _get_manager()

    if method == "put":
        agent = params["agent"]
        bucket = params["bucket"]
        sub_path = params["sub_path"]
        value = params["value"]
        await mgr.put(agent, bucket, sub_path, value)
        return "ok"

    elif method == "get":
        agent = params["agent"]
        bucket = params["bucket"]
        sub_path = params["sub_path"]
        return await mgr.get(agent, bucket, sub_path)

    elif method == "list_keys":
        agent = params["agent"]
        bucket = params["bucket"]
        prefix = params.get("prefix", "")
        return await mgr.list_keys(agent, bucket, prefix)

    elif method == "delete":
        agent = params["agent"]
        bucket = params["bucket"]
        sub_path = params["sub_path"]
        return await mgr.delete(agent, bucket, sub_path)

    elif method == "agent_stats":
        agent = params["agent"]
        return await mgr.agent_stats(agent)

    else:
        raise ValueError(
            f"Unknown method {method!r}. "
            "Valid methods: put, get, list_keys, delete, agent_stats"
        )


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single client connection: read one request, write one response."""
    peer = writer.get_extra_info("peername", "<unknown>")
    try:
        data = await asyncio.wait_for(reader.read(65536), timeout=5.0)
        if not data:
            logger.debug("soulmgrd: empty request from %s", peer)
            return

        try:
            req = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as parse_err:
            response = {"error": f"JSON parse error: {parse_err}"}
            writer.write(json.dumps(response).encode("utf-8"))
            await writer.drain()
            return

        try:
            result = await _dispatch(req)
            response = {"result": result}
        except (KeyError, ValueError) as dispatch_err:
            logger.warning("soulmgrd: bad request from %s: %s", peer, dispatch_err)
            response = {"error": str(dispatch_err)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("soulmgrd: handler error for %s: %s", peer, exc)
            response = {"error": f"internal error: {exc}"}

        writer.write(json.dumps(response).encode("utf-8"))
        await writer.drain()

    except asyncio.TimeoutError:
        logger.warning("soulmgrd: timeout reading from %s", peer)
        try:
            writer.write(json.dumps({"error": "timeout"}).encode("utf-8"))
            await writer.drain()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("soulmgrd: unexpected error from %s: %s", peer, exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


async def main() -> None:
    """Start the soulmgrd TCP server and serve forever."""
    # Pre-create the SoulManager so first-request latency is minimal.
    _get_manager()

    server = await asyncio.start_server(
        handle_client,
        SOUL_MGR_HOST,
        SOUL_MGR_PORT,
    )
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    logger.info("soulmgrd listening on %s (ADR-0002 §3 Memory Continuity System)", addrs)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(main())
