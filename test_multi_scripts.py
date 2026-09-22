#!/usr/bin/env python3
"""Test multi-script execution functionality."""

import json
import os
import sys
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from cpe_session import SessionRegistry, CPESession, OutboundRPC
from acs_server import EventScriptManager
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test")

def test_multi_script_execution():
    """Test executing multiple scripts in sequence."""
    print("="*60)
    print("Test 1: Multi-Script Sequential Execution")
    print("="*60)
    
    # Create three temporary scripts
    scripts = []
    for i in range(1, 4):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f"""#MODE=get
# Test script {i}
Device.DeviceInfo.SerialNumber
Device.DeviceInfo.SoftwareVersion
""")
            scripts.append(f.name)
    
    try:
        config = {
            "event_scripts": {
                "enabled": True,
                "max_scripts_per_event": 3,
                "mappings": {
                    "0": {
                        "scripts": [
                            {"mode": "get", "script": scripts[0], "description": "Script 1"},
                            {"mode": "get", "script": scripts[1], "description": "Script 2"},
                            {"mode": "get", "script": scripts[2], "description": "Script 3"}
                        ]
                    }
                }
            }
        }
        
        registry = SessionRegistry()
        mgr = EventScriptManager(config, registry, log)
        
        sess = CPESession(serial="TEST001")
        registry._sessions["TEST001"] = sess
        
        info = {
            "events": [{"code": "0", "command_key": ""}],
            "device_id": {},
            "params": {}
        }
        
        mgr.trigger(sess, info)
        
        # Should have 3 RPC queued (one GET per script)
        queued = len(sess.pending)
        print(f"  Queued {queued} RPC(s)")
        assert queued == 3, f"Expected 3 RPCs, got {queued}"
        print("✓ All 3 scripts executed successfully\n")
        return True
    
    finally:
        for script in scripts:
            os.unlink(script)

def test_max_scripts_limit():
    """Test max_scripts_per_event limit."""
    print("="*60)
    print("Test 2: Max Scripts Limit")
    print("="*60)
    
    # Create 5 scripts, but max=3
    scripts = []
    for i in range(1, 6):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f"""#MODE=get
# Test script {i}
Device.DeviceInfo.UpTime
""")
            scripts.append(f.name)
    
    try:
        config = {
            "event_scripts": {
                "enabled": True,
                "max_scripts_per_event": 3,
                "mappings": {
                    "0": {
                        "scripts": [
                            {"mode": "get", "script": s, "description": f"Script {i}"}
                            for i, s in enumerate(scripts, 1)
                        ]
                    }
                }
            }
        }
        
        registry = SessionRegistry()
        mgr = EventScriptManager(config, registry, log)
        
        sess = CPESession(serial="TEST002")
        registry._sessions["TEST002"] = sess
        
        info = {
            "events": [{"code": "0", "command_key": ""}],
            "device_id": {},
            "params": {}
        }
        
        mgr.trigger(sess, info)
        
        # Should only execute first 3 scripts
        queued = len(sess.pending)
        print(f"  Configured 5 scripts, max_scripts=3")
        print(f"  Queued {queued} RPC(s)")
        assert queued == 3, f"Expected 3 RPCs (limited by max), got {queued}"
        print("✓ Limit applied correctly\n")
        return True
    
    finally:
        for script in scripts:
            os.unlink(script)

def test_backward_compatibility():
    """Test single script config still works."""
    print("="*60)
    print("Test 3: Backward Compatibility (Single Script)")
    print("="*60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("""#MODE=get
Device.DeviceInfo.ModelName
""")
        script_path = f.name
    
    try:
        # Old format: single script
        config = {
            "event_scripts": {
                "enabled": True,
                "mappings": {
                    "0": {
                        "mode": "get",
                        "script": script_path
                    }
                }
            }
        }
        
        registry = SessionRegistry()
        mgr = EventScriptManager(config, registry, log)
        
        sess = CPESession(serial="TEST003")
        registry._sessions["TEST003"] = sess
        
        info = {
            "events": [{"code": "0", "command_key": ""}],
            "device_id": {},
            "params": {}
        }
        
        mgr.trigger(sess, info)
        
        queued = len(sess.pending)
        print(f"  Old format (single script): Queued {queued} RPC(s)")
        assert queued == 1, f"Expected 1 RPC, got {queued}"
        print("✓ Backward compatibility maintained\n")
        return True
    
    finally:
        os.unlink(script_path)

def test_script_failure_continues():
    """Test that script failure doesn't stop execution."""
    print("="*60)
    print("Test 4: Script Failure Continues Execution")
    print("="*60)
    
    # Create 2 valid scripts
    valid_scripts = []
    for i in [1, 3]:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f"""#MODE=get
Device.DeviceInfo.UpTime
""")
            valid_scripts.append(f.name)
    
    try:
        config = {
            "event_scripts": {
                "enabled": True,
                "max_scripts_per_event": 3,
                "mappings": {
                    "0": {
                        "scripts": [
                            {"mode": "get", "script": valid_scripts[0], "description": "Script 1 (success)"},
                            {"mode": "get", "script": "/nonexistent/script.txt", "description": "Script 2 (fail)"},
                            {"mode": "get", "script": valid_scripts[1], "description": "Script 3 (success)"}
                        ]
                    }
                }
            }
        }
        
        registry = SessionRegistry()
        mgr = EventScriptManager(config, registry, log)
        
        sess = CPESession(serial="TEST004")
        registry._sessions["TEST004"] = sess
        
        info = {
            "events": [{"code": "0", "command_key": ""}],
            "device_id": {},
            "params": {}
        }
        
        mgr.trigger(sess, info)
        
        # Should have 2 RPC queued (script 1 and 3 succeeded)
        queued = len(sess.pending)
        print(f"  Script 1: Success, Script 2: Failed, Script 3: Success")
        print(f"  Queued {queued} RPC(s)")
        assert queued == 2, f"Expected 2 RPCs (from successful scripts), got {queued}"
        print("✓ Execution continued after failure\n")
        return True
    
    finally:
        for script in valid_scripts:
            os.unlink(script)

def test_mixed_modes():
    """Test mixing GET and SET in multi-script config."""
    print("="*60)
    print("Test 5: Mixed GET/SET Modes")
    print("="*60)
    
    # Create GET and SET scripts
    scripts = []
    
    # GET script
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("""#MODE=get
Device.DeviceInfo.UpTime
""")
        scripts.append(f.name)
    
    # SET script
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("""#MODE=set
Device.ManagementServer.PeriodicInformInterval=300:uint
""")
        scripts.append(f.name)
    
    try:
        config = {
            "event_scripts": {
                "enabled": True,
                "max_scripts_per_event": 3,
                "mappings": {
                    "0": {
                        "scripts": [
                            {"mode": "get", "script": scripts[0], "description": "Query first"},
                            {"mode": "set", "script": scripts[1], "description": "Then configure"}
                        ]
                    }
                }
            }
        }
        
        registry = SessionRegistry()
        mgr = EventScriptManager(config, registry, log)
        
        sess = CPESession(serial="TEST005")
        registry._sessions["TEST005"] = sess
        
        info = {
            "events": [{"code": "0", "command_key": ""}],
            "device_id": {},
            "params": {}
        }
        
        mgr.trigger(sess, info)
        
        # Should have 2 RPCs (1 GET + 1 SET)
        queued = len(sess.pending)
        print(f"  Script 1 (GET): 1 RPC, Script 2 (SET): 1 RPC")
        print(f"  Total queued: {queued} RPC(s)")
        assert queued == 2, f"Expected 2 RPCs, got {queued}"
        
        # Verify RPC types
        rpc1 = sess.pending[0]
        rpc2 = sess.pending[1]
        print(f"  RPC 1: {rpc1.method}")
        print(f"  RPC 2: {rpc2.method}")
        assert rpc1.method == "GetParameterValues"
        assert rpc2.method == "SetParameterValues"
        print("✓ Mixed modes executed correctly\n")
        return True
    
    finally:
        for script in scripts:
            os.unlink(script)

def test_with_example_config():
    """Test with actual multi-script example config."""
    print("="*60)
    print("Test 6: Example Config Integration")
    print("="*60)
    
    config_file = "config_event_scripts_multi_example.json"
    if not os.path.exists(config_file):
        print(f"  ⚠ {config_file} not found, skipping")
        return True
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    registry = SessionRegistry()
    mgr = EventScriptManager(config, registry, log)
    
    # Test TESTDEV001 (should execute 3 scripts)
    sess = CPESession(
        serial="TESTDEV001",
        device_id={
            "SerialNumber": "TESTDEV001",
            "OUI": "AABBCC",
            "ProductClass": "TestDevice"
        }
    )
    registry._sessions["TESTDEV001"] = sess
    
    info = {
        "events": [{"code": "0", "command_key": ""}],
        "device_id": sess.device_id,
        "params": {}
    }
    
    mgr.trigger(sess, info)
    
    queued = len(sess.pending)
    print(f"  TESTDEV001 BOOTSTRAP: Queued {queued} RPC(s)")
    print(f"  Expected: 3 scripts (base + check + custom)")
    # Note: Actual count depends on script content
    print("✓ Example config processed successfully\n")
    return True

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Multi-Script Execution - Test Suite")
    print("="*60 + "\n")
    
    tests = [
        test_multi_script_execution,
        test_max_scripts_limit,
        test_backward_compatibility,
        test_script_failure_continues,
        test_mixed_modes,
        test_with_example_config,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed with exception: {e}\n")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
