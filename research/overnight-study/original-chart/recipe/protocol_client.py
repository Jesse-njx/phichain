"""Portable official MCP SDK transport; run with an interpreter having the server installed."""
import sys
from contextlib import asynccontextmanager
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
@asynccontextmanager
async def connect(python=None):
    async with stdio_client(StdioServerParameters(command=python or sys.executable,args=['-m','phigros_chart_mcp.server'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize();yield session
