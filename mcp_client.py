#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""麦当劳 MCP 最小客户端：python mcp_client.py <tool> ['{"json":...}']

Token 安全：从环境变量 MCD_MCP_TOKEN 读取（或 --token=xxx 传入）。
Token 永远不写进代码、不进 Git 仓库。
  Windows PowerShell:  $env:MCD_MCP_TOKEN = "你的Token"
  Windows Git Bash:    export MCD_MCP_TOKEN="你的Token"
  Linux / macOS:       export MCD_MCP_TOKEN="你的Token"
"""
import os
import sys
import json
import urllib.request

ENDPOINT = "https://mcp.mcd.cn"
TOKEN = os.environ.get("MCD_MCP_TOKEN", "")

def call(method, params, rid=1):
    if not TOKEN:
        print(json.dumps({
            "_error": "缺少 MCP Token：请先设置环境变量 MCD_MCP_TOKEN"
                      "（获取方式见 README「获取你自己的 Token」），或使用 --demo 模式离线体验。"
        }, ensure_ascii=False))
        sys.exit(2)
    payload = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}).encode()
    req = urllib.request.Request(ENDPOINT, data=payload, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + TOKEN,
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def tool(name, args=None, rid=1):
    out = call("tools/call", {"name": name, "arguments": args or {}}, rid)
    if "error" in out:
        return {"_error": out["error"]}
    content = out.get("result", {})
    texts = [c.get("text", "") for c in content.get("content", []) if c.get("type") == "text"]
    parsed = []
    for tx in texts:
        try:
            parsed.append(json.loads(tx))
        except Exception:
            parsed.append(tx)
    return {"structured": content.get("structuredContent"), "texts": parsed}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    if name == "_init":
        print(json.dumps(call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "mcd-script-forge", "version": "0.1.0"}}), ensure_ascii=False))
    else:
        print(json.dumps(tool(name, args), ensure_ascii=False, indent=1))
