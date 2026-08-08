import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs

# Global state for endpoints
live_status = {"code": 200, "label": "200 OK"}
test_status = {"speed": "normal"}

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AetherCloud Portal - Dynamic Subdomains</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Plus+Jakarta+Sans:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary-glow: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, rgba(99, 102, 241, 0) 70%);
            --accent-purple: #8b5cf6;
            --accent-indigo: #6366f1;
            --success-color: #10b981;
            --error-color: #ef4444;
            --warning-color: #f59e0b;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow-x: hidden;
            position: relative;
            padding: 2rem;
        }

        .glow-bg {
            position: absolute; top: 0; left: 15%;
            width: 600px; height: 600px;
            background: var(--primary-glow);
            z-index: -1; filter: blur(80px);
        }

        .container { width: 100%; max-width: 800px; z-index: 10; }

        header { text-align: center; margin-bottom: 3rem; }
        h1 {
            font-family: 'Outfit', sans-serif; font-size: 2.5rem; font-weight: 800;
            background: linear-gradient(135deg, #ffffff 30%, #a5b4fc 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        p.subtitle { color: var(--text-muted); }

        .dashboard {
            display: flex; flex-direction: column; gap: 2rem;
        }

        .panel {
            background: var(--card-bg); border: 1px solid var(--border-color);
            border-radius: 24px; padding: 2rem; backdrop-filter: blur(20px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }

        .panel-header {
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid var(--border-color); padding-bottom: 1rem; margin-bottom: 1.5rem;
        }
        .panel-title {
            font-family: 'Outfit', sans-serif; font-size: 1.5rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem;
        }
        
        .status-badge {
            font-family: 'Courier New', monospace; font-size: 0.9rem; font-weight: bold;
            padding: 0.25rem 0.75rem; border-radius: 8px;
        }
        .badge-200, .badge-normal { background: rgba(16, 185, 129, 0.15); color: var(--success-color); }
        .badge-500, .badge-slow { background: rgba(239, 68, 68, 0.15); color: var(--error-color); }
        .badge-404 { background: rgba(245, 158, 11, 0.15); color: var(--warning-color); }

        .controls-row {
            display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1rem;
        }

        .btn {
            font-family: 'Outfit', sans-serif; font-size: 0.95rem; font-weight: 600;
            padding: 0.75rem 1.5rem; border-radius: 12px; border: none; cursor: pointer;
            transition: all 0.2s ease;
        }
        .btn-success { background: rgba(16, 185, 129, 0.2); color: var(--success-color); border: 1px solid var(--success-color); }
        .btn-success:hover { background: var(--success-color); color: white; }
        
        .btn-error { background: rgba(239, 68, 68, 0.2); color: var(--error-color); border: 1px solid var(--error-color); }
        .btn-error:hover { background: var(--error-color); color: white; }
        
        .btn-warning { background: rgba(245, 158, 11, 0.2); color: var(--warning-color); border: 1px solid var(--warning-color); }
        .btn-warning:hover { background: var(--warning-color); color: white; }

        .btn-primary { background: rgba(99, 102, 241, 0.2); color: var(--accent-indigo); border: 1px solid var(--accent-indigo); }
        .btn-primary:hover { background: var(--accent-indigo); color: white; }
    </style>
</head>
<body>
    <div class="glow-bg"></div>
    <div class="container">
        <header>
            <h1>AetherCloud Subdomain Controls</h1>
            <p class="subtitle">Dynamically modify endpoint behavior for the monitor to detect.</p>
        </header>

        <div class="dashboard">
            <!-- LIVE PANEL -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">&#128308; /live Subdomain</div>
                    <span id="live-badge" class="status-badge badge-200">200 OK</span>
                </div>
                <p>Modify the HTTP status code returned by the <code>/live</code> endpoint.</p>
                <div class="controls-row">
                    <button class="btn btn-success" onclick="setLiveStatus(200, '200 OK')">Set 200 (Success)</button>
                    <button class="btn btn-warning" onclick="setLiveStatus(404, '404 Not Found')">Set 404 (Not Found)</button>
                    <button class="btn btn-error" onclick="setLiveStatus(500, '500 Server Error')">Set 500 (Fail)</button>
                </div>
            </div>

            <!-- TEST PANEL -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">&#9889; /test Subdomain</div>
                    <span id="test-badge" class="status-badge badge-normal">Normal Speed</span>
                </div>
                <p>Modify the latency (response time) of the <code>/test</code> endpoint.</p>
                <div class="controls-row">
                    <button class="btn btn-success" onclick="setTestSpeed('normal')">Set Normal (Fast)</button>
                    <button class="btn btn-error" onclick="setTestSpeed('slow')">Set Slow (5s Delay)</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function setLiveStatus(code, label) {
            try {
                const res = await fetch(`/api/live?code=${code}&label=${encodeURIComponent(label)}`, { method: 'POST' });
                const data = await res.json();
                updateLiveUI(data.code, data.label);
            } catch (err) { console.error(err); }
        }

        async function setTestSpeed(speed) {
            try {
                const res = await fetch(`/api/test?speed=${speed}`, { method: 'POST' });
                const data = await res.json();
                updateTestUI(data.speed);
            } catch (err) { console.error(err); }
        }

        function updateLiveUI(code, label) {
            const badge = document.getElementById('live-badge');
            badge.textContent = label;
            if(code === 200) badge.className = 'status-badge badge-200';
            else if(code === 404) badge.className = 'status-badge badge-404';
            else badge.className = 'status-badge badge-500';
        }

        function updateTestUI(speed) {
            const badge = document.getElementById('test-badge');
            if(speed === 'normal') {
                badge.textContent = 'Normal Speed';
                badge.className = 'status-badge badge-normal';
            } else {
                badge.textContent = 'Slow Speed';
                badge.className = 'status-badge badge-slow';
            }
        }

        // Fetch initial state
        fetch('/api/status').then(r => r.json()).then(data => {
            updateLiveUI(data.live.code, data.live.label);
            updateTestUI(data.test.speed);
        });
    </script>
</body>
</html>
"""

class MockServerRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))

        elif parsed_path.path == '/live':
            code = live_status["code"]
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Status: {live_status['label']}".encode('utf-8'))

        elif parsed_path.path == '/test':
            if test_status["speed"] == "slow":
                print("[Test Server] Simulating latency... Sleeping for 5 seconds.")
                time.sleep(5)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Test endpoint response.")

        elif parsed_path.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"live": live_status, "test": test_status}).encode('utf-8'))

        else:
            # Fallback for old monitor endpoints
            if parsed_path.path in ['/success', '/fail', '/notfound', '/slow']:
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"This endpoint is deprecated in the new subdomain architecture.")
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Not Found")

    def do_POST(self):
        parsed_path = urlparse(self.path)
        qs = parse_qs(parsed_path.query)

        if parsed_path.path == '/api/live':
            code = int(qs.get('code', ['200'])[0])
            label = qs.get('label', ['200 OK'])[0]
            live_status["code"] = code
            live_status["label"] = label
            print(f"[Test Server] /live updated to {code} ({label})")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(live_status).encode('utf-8'))

        elif parsed_path.path == '/api/test':
            speed = qs.get('speed', ['normal'])[0]
            test_status["speed"] = speed
            print(f"[Test Server] /test speed updated to {speed}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(test_status).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=8080):
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, MockServerRequestHandler)
    print(f"[Test Server] Running new Subdomain Mock Server on http://0.0.0.0:{port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Test Server] Shutting down mock server.")
        httpd.server_close()

if __name__ == '__main__':
    import sys
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
