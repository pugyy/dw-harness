"""dw-harness core: shared by CLI, Claude Code hooks, CI and MCP.

Standard-library only at this layer. Optional capabilities (YAML contracts,
deep SQL parsing, database clients) degrade gracefully and are reported as
"unavailable" instead of raising.
"""

__version__ = "2.0.1"

EVIDENCE_SCHEMA = "dw-evidence/2"
CONTRACT_SCHEMA = "dw-contract/2"
