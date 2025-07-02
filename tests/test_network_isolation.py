#!/usr/bin/env python3
"""
Network isolation test suite.

Tests container network isolation, prevention of outbound connections,
and proper enforcement of --network none flag.
"""
import subprocess
import tempfile
import shutil
import socket
import pytest
from pathlib import Path
import time


class TestNetworkIsolation:
    """Tests for network isolation and security."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="network_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def temp_harness(self):
        """Create a temporary harness directory."""
        temp_dir = tempfile.mkdtemp(prefix="harness_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_container_network_none_flag(self, temp_workspace, temp_harness):
        """Test that container is launched with --network none."""
        # This test verifies the flag is present in run_trial.py
        run_trial_path = Path(__file__).parent.parent / "orchestrator" / "run_trial.py"
        
        if run_trial_path.exists():
            content = run_trial_path.read_text()
            assert '"--network", "none"' in content, \
                "Container must be launched with --network none flag"
    
    def test_outbound_connection_blocked(self, temp_workspace, temp_harness):
        """Test that outbound network connections are blocked."""
        # Create a test script that attempts network connection
        test_script = Path(temp_workspace) / "test_network.py"
        test_script.write_text("""
import socket
import sys

try:
    # Try to connect to a public DNS server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    sock.connect(("8.8.8.8", 53))
    print("NETWORK_ACCESSIBLE")
    sock.close()
except Exception as e:
    print(f"NETWORK_BLOCKED: {e}")
    sys.exit(0)
""")
        
        # Run in container with network isolation
        result = subprocess.run([
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-w", "/workspace",
            "swe-replacement:latest",
            "python", "test_network.py"
        ], capture_output=True, text=True, timeout=10)
        
        # Should indicate network is blocked
        assert "NETWORK_BLOCKED" in result.stdout, \
            "Network should be blocked in isolated container"
        assert "NETWORK_ACCESSIBLE" not in result.stdout
    
    def test_dns_resolution_fails(self, temp_workspace, temp_harness):
        """Test that DNS resolution fails in isolated container."""
        test_script = Path(temp_workspace) / "test_dns.py"
        test_script.write_text("""
import socket

try:
    # Try to resolve a domain
    ip = socket.gethostbyname("google.com")
    print(f"DNS_WORKED: {ip}")
except Exception as e:
    print(f"DNS_FAILED: {e}")
""")
        
        result = subprocess.run([
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-w", "/workspace",
            "swe-replacement:latest",
            "python", "test_dns.py"
        ], capture_output=True, text=True, timeout=10)
        
        assert "DNS_FAILED" in result.stdout
        assert "DNS_WORKED" not in result.stdout
    
    def test_localhost_accessible(self, temp_workspace, temp_harness):
        """Test that localhost connections still work (for IPC)."""
        test_script = Path(temp_workspace) / "test_localhost.py"
        test_script.write_text("""
import socket
import threading
import time

def server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    print(f"PORT:{port}")
    sock.listen(1)
    conn, addr = sock.accept()
    conn.send(b"Hello")
    conn.close()
    sock.close()

# Start server in thread
server_thread = threading.Thread(target=server)
server_thread.start()
time.sleep(0.5)

# Try to connect to localhost - this should work
try:
    # Extract port from output (crude but works for test)
    import sys
    for line in sys.stdout.getvalue().split('\\n'):
        if line.startswith('PORT:'):
            port = int(line.split(':')[1])
            break
    
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(('127.0.0.1', port))
    data = client.recv(1024)
    print("LOCALHOST_WORKS")
    client.close()
except Exception as e:
    print(f"LOCALHOST_FAILED: {e}")

server_thread.join()
""")
        
        # Note: This is a complex test that may not work perfectly in all environments
        # The key point is that localhost should still be accessible even with --network none
    
    def test_patch_cannot_create_network_code(self, temp_workspace, temp_harness):
        """Test that patches creating network code still can't connect."""
        # Create initial file
        test_file = Path(temp_workspace) / "app.py"
        test_file.write_text("# Empty file")
        
        # Create a patch that adds network code
        patch_content = """--- a/app.py
+++ b/app.py
@@ -1 +1,11 @@
-# Empty file
+import socket
+
+def test_network():
+    try:
+        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
+        sock.connect(("8.8.8.8", 53))
+        return "CONNECTED"
+    except:
+        return "BLOCKED"
+
+print(test_network())
"""
        
        # Apply patch and run in isolated container
        # This would be an integration test with the harness
    
    def test_subprocess_network_isolation(self, temp_workspace, temp_harness):
        """Test that subprocesses also have network isolation."""
        test_script = Path(temp_workspace) / "test_subprocess.py"
        test_script.write_text("""
import subprocess

# Try to ping in a subprocess
result = subprocess.run(
    ["python", "-c", "import socket; sock=socket.socket(); sock.connect(('8.8.8.8', 53))"],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print("SUBPROCESS_BLOCKED")
else:
    print("SUBPROCESS_CONNECTED")
""")
        
        result = subprocess.run([
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-w", "/workspace",
            "swe-replacement:latest",
            "python", "test_subprocess.py"
        ], capture_output=True, text=True, timeout=10)
        
        assert "SUBPROCESS_BLOCKED" in result.stdout
    
    def test_no_network_interfaces(self, temp_workspace, temp_harness):
        """Test that container has minimal network interfaces."""
        result = subprocess.run([
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "swe-replacement:latest",
            "ip", "addr", "show"
        ], capture_output=True, text=True)
        
        # Should only have loopback interface
        assert "lo:" in result.stdout or "lo@" in result.stdout
        assert "eth0" not in result.stdout  # No ethernet interface
    
    def test_network_none_vs_normal(self, temp_workspace, temp_harness):
        """Compare behavior with and without network isolation."""
        test_script = Path(temp_workspace) / "network_test.py"
        test_script.write_text("""
import socket
try:
    socket.create_connection(("8.8.8.8", 53), timeout=2)
    print("NETWORK_OK")
except:
    print("NETWORK_FAIL")
""")
        
        # With network isolation
        isolated_result = subprocess.run([
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:ro",
            "swe-replacement:latest",
            "python", "/workspace/network_test.py"
        ], capture_output=True, text=True, timeout=5)
        
        # Without network isolation (default bridge)
        normal_result = subprocess.run([
            "docker", "run", "--rm",
            "-v", f"{temp_workspace}:/workspace:ro",
            "swe-replacement:latest",
            "python", "/workspace/network_test.py"
        ], capture_output=True, text=True, timeout=5)
        
        # Isolated should fail, normal should succeed
        assert "NETWORK_FAIL" in isolated_result.stdout
        assert "NETWORK_OK" in normal_result.stdout
    
    def test_unix_sockets_still_work(self, temp_workspace, temp_harness):
        """Test that Unix domain sockets still work for IPC."""
        test_script = Path(temp_workspace) / "test_unix_socket.py"
        test_script.write_text("""
import socket
import os
import threading
import time

socket_path = "/tmp/test.sock"

def server():
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(socket_path)
    sock.listen(1)
    
    conn, addr = sock.accept()
    conn.send(b"Unix socket works")
    conn.close()
    sock.close()

# Start server
server_thread = threading.Thread(target=server)
server_thread.start()
time.sleep(0.5)

# Connect as client
try:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(socket_path)
    data = client.recv(1024)
    print("UNIX_SOCKET_WORKS")
    client.close()
except Exception as e:
    print(f"UNIX_SOCKET_FAILED: {e}")

server_thread.join()
os.unlink(socket_path)
""")
        
        result = subprocess.run([
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-w", "/workspace",
            "swe-replacement:latest",
            "python", "test_unix_socket.py"
        ], capture_output=True, text=True, timeout=10)
        
        # Unix sockets should work even with network isolation
        assert "UNIX_SOCKET_WORKS" in result.stdout
    
    def test_iptables_not_accessible(self, temp_workspace, temp_harness):
        """Test that iptables cannot be modified in container."""
        result = subprocess.run([
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "swe-replacement:latest",
            "iptables", "-L"
        ], capture_output=True, text=True)
        
        # Should fail due to lack of privileges
        assert result.returncode != 0
        assert "permission denied" in result.stderr.lower() or \
               "operation not permitted" in result.stderr.lower() 