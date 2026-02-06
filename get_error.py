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
# Get activities for failed session
resp = c.call("jules_list_activities", {"session_id": "2658405090531501308"})
print(json.dumps(resp, indent=2)[:2000])
c.close()
