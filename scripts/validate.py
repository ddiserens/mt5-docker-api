#!/usr/bin/env python3
"""
Full validation script for MT5 Docker API
"""
import sys
import time
import requests
import subprocess
import json
from datetime import datetime

class Validator:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.vnc_url = "http://localhost:3000"
        self.errors = []
        self.warnings = []
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
    def check_port(self, port, service):
        """Verify if a port is open"""
        try:
            result = subprocess.run(
                ["nc", "-zv", "localhost", str(port)],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.log(f"✓ Port {port} ({service}) is open")
                return True
            else:
                self.log(f"✗ Port {port} ({service}) is not accessible", "ERROR")
                self.errors.append(f"Port {port} ({service}) not accessible")
                return False
        except Exception as e:
            self.log(f"✗ Error checking port {port}: {e}", "ERROR")
            self.errors.append(f"Error checking port {port}")
            return False
    
    def check_vnc(self):
        """Verify VNC access"""
        self.log("Verifying VNC access...")
        try:
            response = requests.get(self.vnc_url, timeout=10)
            if response.status_code == 200:
                self.log("✓ VNC web interface is accessible")
                return True
            else:
                self.log(f"✗ VNC returned code {response.status_code}", "ERROR")
                self.errors.append(f"VNC status code: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"✗ Error accessing VNC: {e}", "ERROR")
            self.errors.append(f"VNC error: {str(e)}")
            return False
    
    def check_api_health(self):
        """Verify API health endpoint"""
        self.log("Verifying API health...")
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    self.log("✓ API is healthy")
                    if data.get("mt5_connected"):
                        self.log("✓ MT5 is connected")
                    else:
                        self.log("⚠ MT5 is not connected", "WARNING")
                        self.warnings.append("MT5 not connected")
                    return True
                else:
                    self.log("✗ API reports unhealthy status", "ERROR")
                    self.errors.append("API unhealthy")
                    return False
            else:
                self.log(f"✗ API health returned code {response.status_code}", "ERROR")
                self.errors.append(f"API health status: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"✗ Error accessing API health: {e}", "ERROR")
            self.errors.append(f"API health error: {str(e)}")
            return False
    
    def check_api_docs(self):
        """Verify API documentation"""
        self.log("Verifying API documentation...")
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=10)
            if response.status_code == 200:
                self.log("✓ API documentation is accessible")
                return True
            else:
                self.log(f"✗ Docs returned code {response.status_code}", "ERROR")
                self.errors.append(f"API docs status: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"✗ Error accessing docs: {e}", "ERROR")
            self.errors.append(f"API docs error: {str(e)}")
            return False
    
    def check_api_endpoints(self):
        """Verify main API endpoints"""
        endpoints = [
            ("/symbols", "GET", None),
            ("/account", "GET", None),
            ("/positions", "GET", None),
        ]
        
        self.log("Verifying API endpoints...")
        all_ok = True
        
        for endpoint, method, data in endpoints:
            try:
                if method == "GET":
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                elif method == "POST":
                    response = requests.post(
                        f"{self.base_url}{endpoint}", 
                        json=data, 
                        timeout=10
                    )
                
                if response.status_code in [200, 404]:  # 404 is OK for empty data
                    self.log(f"✓ {method} {endpoint} - OK ({response.status_code})")
                else:
                    self.log(f"✗ {method} {endpoint} - Error ({response.status_code})", "ERROR")
                    self.errors.append(f"{method} {endpoint}: {response.status_code}")
                    all_ok = False
                    
            except Exception as e:
                self.log(f"✗ {method} {endpoint} - Error: {e}", "ERROR")
                self.errors.append(f"{method} {endpoint}: {str(e)}")
                all_ok = False
        
        return all_ok
    
    def check_websocket(self):
        """Verify WebSocket endpoint"""
        self.log("Verifying WebSocket...")
        try:
            import websocket
            
            ws = websocket.WebSocket()
            ws.connect("ws://localhost:8000/ws/ticks/EURUSD", timeout=5)
            
            # Wait for a message
            ws.settimeout(5)
            try:
                message = ws.recv()
                data = json.loads(message)
                if "symbol" in data:
                    self.log("✓ WebSocket is functional")
                    ws.close()
                    return True
            except websocket.WebSocketTimeoutException:
                self.log("⚠ WebSocket connected but no data received", "WARNING")
                self.warnings.append("WebSocket no data")
                ws.close()
                return True
                
        except ImportError:
            self.log("⚠ websocket module not installed, skipping test", "WARNING")
            self.warnings.append("WebSocket not tested")
            return True
        except Exception as e:
            self.log(f"✗ Error with WebSocket: {e}", "ERROR")
            self.errors.append(f"WebSocket error: {str(e)}")
            return False
    
    def run_all_checks(self):
        """Run all validations"""
        self.log("=== Starting full validation ===")
        
        # Wait for services to start
        self.log("Waiting 10 seconds for services to start...")
        time.sleep(10)
        
        # Verify ports
        ports_ok = all([
            self.check_port(3000, "VNC"),
            self.check_port(8000, "API"),
            self.check_port(8001, "MT5")
        ])
        
        if not ports_ok:
            self.log("Some ports are not available", "WARNING")
        
        # Verify services
        self.check_vnc()
        self.check_api_health()
        self.check_api_docs()
        self.check_api_endpoints()
        self.check_websocket()
        
        # Summary
        self.log("=== Validation Summary ===")
        
        if self.errors:
            self.log(f"Errors found: {len(self.errors)}", "ERROR")
            for error in self.errors:
                self.log(f"  - {error}", "ERROR")
        
        if self.warnings:
            self.log(f"Warnings: {len(self.warnings)}", "WARNING")
            for warning in self.warnings:
                self.log(f"  - {warning}", "WARNING")
        
        if not self.errors:
            self.log("✓ All validations passed successfully!", "SUCCESS")
            return 0
        else:
            self.log("✗ Errors were found in the validation", "ERROR")
            return 1

if __name__ == "__main__":
    validator = Validator()
    sys.exit(validator.run_all_checks())
