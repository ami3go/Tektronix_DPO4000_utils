"""Optional MCP integration for DPO4000 instruments.

Importing this package does not import the MCP SDK, connect to VISA, or start a
server. Install the `mcp` extra to use the protocol adapter.
"""

from .gateway import ReadOnlyGateway, ScopeBusyError, ScopeIOForbiddenError

__all__ = ["ReadOnlyGateway", "ScopeBusyError", "ScopeIOForbiddenError"]
