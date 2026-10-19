"""MCP server: lets an agent read (and, if allowed, triage) Jobs Radar over stdio (ADR-078).

The package is a thin client of the REST API. It never imports the application layers; the
import-linter contract ``The MCP server only talks to the API`` enforces that.
"""
