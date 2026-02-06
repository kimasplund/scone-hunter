#!/usr/bin/env python3
"""Check Jules session status and timing."""
import json, subprocess, time
from pathlib import Path
from threading import Thread
from queue import Queue, Empty

MCP_SERVER = str(Path.home() / ".local/bin/jules-mcp-server")

class JulesClient:
    def __init__(self):
        self.proc = None
        self.responses = Queue()
        self.req_id = 0
    
    def start(self):
        self.proc = subprocess.Popen([MCP_SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        Thread(target=self._read, daemon=True).start()
        time.sleep(1)
        self._send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"checker","version":"1.0"}}})
        self._wait(10)
        self._send({"jsonrpc":"2.0","method":"notifications/initialized"})
        return True
    
    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg)+"\n")
        self.proc.stdin.flush()
    
    def _read(self):
        while self.proc and self.proc.stdout:
            line = self.proc.stdout.readline().strip()
            if line.startswith("{"): self.responses.put(json.loads(line))
    
    def _wait(self, timeout=30):
        try: return self.responses.get(timeout=timeout)
        except Empty: return None
    
    def call(self, name, args=None):
        self.req_id += 1
        self._send({"jsonrpc":"2.0","id":self.req_id,"method":"tools/call","params":{"name":name,"arguments":args or {}}})
        start = time.time()
        while time.time()-start < 30:
            r = self._wait(5)
            if r and r.get("id") == self.req_id: return r
        return {"error":"timeout"}
    
    def close(self):
        if self.proc: self.proc.terminate()

c = JulesClient()
c.start()

# Get all sessions
print("📊 JULES SESSION STATUS")
print("="*60)

resp = c.call("jules_list_sessions", {"filter_by_tags": ["security-hunt"]})
if "result" in resp:
    content = resp["result"].get("content", [])
    if content:
        data = json.loads(content[0].get("text", "{}"))
        sessions = data.get("sessions", [])
        print(f"Active sessions: {len(sessions)}\n")
        for s in sessions:
            sid = s.get("id", "?")
            state = s.get("state", "UNKNOWN")
            title = s.get("title", s.get("prompt", "")[:50])
            created = s.get("createTime", "?")[:19]
            print(f"  {sid}")
            print(f"    State: {state}")
            print(f"    Title: {title[:60]}...")
            print(f"    Created: {created}")
            print()

c.close()
