#!/usr/bin/env python3
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import os

HOTSPOT_NAME = "Pi4-AP"
HOTSPOT_PASSWORD = "12345678"
AP_IFACE = "ap0"
WLAN_IFACE = "wlan0"
HTTP_PORT = 80
HTML_FILE = "templates/index.html"

def load_html_template():
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "<html><body><h1>Error</h1><p>HTML template file not found!</p></body></html>"



def run_cmd(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)

def create_ap0():
    run_cmd(["iw", "dev", WLAN_IFACE, "interface", "add", "ap0", "type", "__ap"])

def start_hotspot():
    create_ap0()
    time.sleep(2)
    run_cmd([
        "nmcli", "device", "wifi", "hotspot",
        "ifname", AP_IFACE,
        "ssid", HOTSPOT_NAME,
        "password", HOTSPOT_PASSWORD
    ])
    time.sleep(2)
    ip = subprocess.check_output(
        ["nmcli","-t","-f","IP4.ADDRESS","device","show",AP_IFACE],
        text=True
    ).strip()
    print(f"Hotspot '{HOTSPOT_NAME}' up on {AP_IFACE}, IP={ip}")

def stop_hotspot():
    run_cmd(["nmcli", "connection", "down", "Hotspot"])
    run_cmd(["iw", "dev", "ap0", "del"])

def connect_station(ssid, password):
    print(f"Connecting to SSID={ssid!r} …")
    result = subprocess.run([
        "nmcli", "device", "wifi", "connect", ssid,
        "password", password, "ifname", WLAN_IFACE
    ], capture_output=True, text=True)
    if result.returncode == 0:
        print("Connected OK; IP config:")
        print(subprocess.check_output(
            ["nmcli","device","show",WLAN_IFACE], text=True
        ))
    else:
        print("Connection failed:", result.stderr)

class CaptivePortal(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/":
            qs = parse_qs(p.query)
            ssid = qs.get("ssid", [None])[0]
            pwd  = qs.get("password", [None])[0]
            if ssid and pwd:
                self.send_response(200)
                self.send_header("Content-Type","text/plain")
                self.end_headers()
                self.wfile.write(f"Received SSID={ssid}, password={pwd}".encode())
                connect_station(ssid, pwd)
                #print("Done—exiting server.")
                #sys.exit(0)
                new_ip = subprocess.check_output(
                        ["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", WLAN_IFACE],
                        text=True
                        ).strip().split(':',1)[1].split('/',1)[0]
                self.send_response(302)
                self.send_header("Location", f"http://{new_ip}/")
                self.end_headers()
                print(f"Redirecting client to http://{new_ip}/ …")
                def delayed_shutdown():
                    time.sleep(2)
                    stop_hotspot()
                    self.server.shutdown()
                    sys.exit(0)
                    
                import threading
                threading.Thread(target=delayed_shutdown, daemon=True).start()
                #stop_hotspot()
                #sys.exit(0)
            else:
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    html_content = load_html_template()
                    self.wfile.write(html_content.encode('utf-8'))

                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(f"Error loading form: {e}".encode())

        elif p.path == "/style.css":
            css_path = os.path.join("templates", "style.css")
            if os.path.isfile(css_path):
                with open(css_path, "rb") as f:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/css")
                    self.end_headers()
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "style.css not found")

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass

def run_server():
    httpd = HTTPServer(("", HTTP_PORT), CaptivePortal)
    print(f"Listening on port {HTTP_PORT} …")
    httpd.serve_forever()

def configure_network():
    start_hotspot()
    run_server()

if __name__ == "__main__":
    start_hotspot()
    run_server()

