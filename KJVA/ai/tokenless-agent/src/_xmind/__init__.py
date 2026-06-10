"""_xmind — Python binding package for the XMIND C inference engine (ADR-0002 §3).

The sovereign inference path: generation runs through the deployed, parity-verified XMIND C
engine via XMindClient. No torch/Python fallback.
"""
from .client import XMindClient, XMindUnavailable, get_client

__all__ = ["XMindClient", "XMindUnavailable", "get_client"]
