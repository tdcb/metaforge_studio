#!/usr/bin/env python3
"""MetaForge Studio — Model Context Protocol (MCP) Server CLI Entrypoint.

Can be launched by any MCP client (Claude Code, Cursor, Kiro, Gemini CLI, Windsurf).
Usage:
  python mcp_server.py
"""
import os
import sys

# Ensure repository root is in python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.agent.mcp_server import run_stdio_mcp_server

if __name__ == "__main__":
    run_stdio_mcp_server()
