"""Run:  python mcp_server.py   -> exposes the FraudX TigerGraph tools over MCP (stdio). Needs: pip install mcp"""
from dotenv import load_dotenv; load_dotenv()
from graph import build_store
from tools import Tools, make_mcp
if __name__ == "__main__": make_mcp(Tools(build_store())).run()
