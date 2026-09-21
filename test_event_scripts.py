#!/usr/bin/env python3
"""Test script for event-driven script execution functionality."""

import json
import os
import sys
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from cpe_session import SessionRegistry, CPESession, OutboundRPC
from acs_server import EventScriptManager
import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("test")

def test_event_script_manager_init():
    """Test EventScriptManager initialization."""
    print("="*60)
    print("Test 1: EventScriptManager Initialization")
    print("="*60)
    
    config = {
        "event_scripts": {
            "enabled": True,
            "timing": "before_response",
            "mappings": {},
        }
    }
    
    registry = SessionRegistry()
    mgr = EventScriptManager(config, registry, log)
    
    assert mgr.enabled == True
    assert mgr.config["timing"] == "before_response"
    print("✓ EventScriptManager initialized successfully\n")
    return True

def test_script_parsing():
    """Test script file parsing."""
    print("="*60)
    print("Test 2: Script File Parsing")
    print("="*60)
    
    # Create temporary script
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("""#MODE=get
# Test script
Device.DeviceInfo.UpTime
Device.DeviceInfo.SoftwareVersion

#MODE=set
Device.ManagementServer.PeriodicInformInterval=300:uint
""")
        script_path = f.name
    
    try:
        config = {
            "event_scripts": {
                "enabled": True,
                "mappings": {
                    "0": {
                        "mode": "auto",
                        "script": script_path
                    }
                }
            }
        }
        
        registry = SessionRegistry()
        mgr = EventScriptManager(config, registry, log)
        
        # Create test session
        sess = CPESession(
            serial="TEST001",
            device_id={
                "SerialNumber": "TEST001",
                "OUI": "AABBCC",
                "ProductClass": "TestCPE"
            }
        )
        registry._sessions["TEST001"] = sess
        
        # Trigger script
        info = {
            "events": [{"code": "0", "command_key": ""}],
            "device_id": sess.device_id,
            "params": {}
        }
        
        mgr.trigger(sess, info)
        
        # Check queued RPCs
        queued = len(sess.pending)
        print(f"  Queued {queued} RPC(s)")
        
        assert queued > 0, "No RPCs queued"
        print("✓ Script parsed and RPCs queued successfully\n")
        return True
    
    finally:
        os.unlink(script_path)

def test_multi_level_fallback():
    """Test multi-level script fallback mechanism."""
    print("="*60)
    print("Test 3: Multi-Level Script Fallback")
    print("="*60)
    
    # Create test scripts
    scripts = {}
    for name in ['default', 'device', 'oui', 'product']:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f"""#MODE=get
# {name} script
Device.DeviceInfo.SerialNumber
""")
            scripts[name] = f.name
    
    try:
        config = {
            "event_scripts": {
                "enabled": True,
                "mappings": {
                    "0": {
                        "mode": "get",
                        "script": scripts['default']
                    }
                },
                "device_overrides": {
                    "DEVICE001": {
                        "0": {
                            "mode": "get",
                            "script": scripts['device']
                        }
                    }
                },
                "oui_overrides": {
                    "AABBCC": {
                        "0": {
                            "mode": "get",
                            "script": scripts['oui']
                        }
                    }
                },
                "product_class_overrides": {
                    "TestCPE": {
                        "0": {
                            "mode": "get",
                            "script": scripts['product']
                        }
                    }
                }
            }
        }
        
        registry = SessionRegistry()
        mgr = EventScriptManager(config, registry, log)
        
        # Test scenarios
        test_cases = [
            ("DEVICE001", "AABBCC", "TestCPE", "device"),  # Device-specific
            ("DEVICE002", "AABBCC", "TestCPE", "oui"),     # OUI-specific
            ("DEVICE003", "XXYYZZ", "TestCPE", "product"), # Product-specific
            ("DEVICE004", "XXYYZZ", "OtherCPE", "default"), # Default
        ]
        
        for serial, oui, pc, expected_script in test_cases:
            sess = CPESession(
                serial=serial,
                device_id={
                    "SerialNumber": serial,
                    "OUI": oui,
                    "ProductClass": pc
                }
            )
            
            found = mgr._find_script(sess, "0")
            if found:
                assert found["script"] == scripts[expected_script], \
                    f"Expected {expected_script}, got {found['script']}"
                print(f"  ✓ {serial}: Using {expected_script} script")
            else:
                print(f"  ✗ {serial}: No script found")
        
        print("✓ Multi-level fallback working correctly\n")
        return True
    
    finally:
        for path in scripts.values():
            os.unlink(path)

def test_mode_detection():
    """Test GET/SET/AUTO mode detection."""
    print("="*60)
    print("Test 4: Mode Detection")
    print("="*60)
    
    test_cases = [
        # (mode, line, expected_operation)
        ("get", "Device.DeviceInfo.UpTime", "GET"),
        ("get", "Device.Time.NTPServer1=time.google.com", "GET"),  # Ignored in GET mode
        ("set", "Device.DeviceInfo.UpTime", "SKIP"),  # No '=' in SET mode
        ("set", "Device.Time.NTPServer1=time.google.com", "SET"),
        ("auto", "Device.DeviceInfo.UpTime", "GET"),
        ("auto", "Device.Time.NTPServer1=time.google.com", "SET"),
    ]
    
    for mode, line, expected in test_cases:
        # Create script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f"#MODE={mode}\n{line}\n")
            script_path = f.name
        
        try:
            config = {
                "event_scripts": {
                    "enabled": True,
                    "mappings": {
                        "0": {
                            "mode": mode,
                            "script": script_path
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
            
            queued = len(sess.pending)
            if expected == "SKIP":
                assert queued == 0, f"Mode {mode}: Expected 0 RPC, got {queued}"
                print(f"  ✓ Mode {mode}, line '{line}': Correctly skipped")
            else:
                assert queued > 0, f"Mode {mode}: No RPC queued"
                rpc = sess.pending[0]
                assert rpc.method == f"{expected.capitalize()}ParameterValues", \
                    f"Expected {expected}, got {rpc.method}"
                print(f"  ✓ Mode {mode}, line '{line}': Correctly detected as {expected}")
            
            # Clear queue
            sess.pending.clear()
        
        finally:
            os.unlink(script_path)
    
    print("✓ Mode detection working correctly\n")
    return True

def test_error_handling():
    """Test error handling."""
    print("="*60)
    print("Test 5: Error Handling")
    print("="*60)
    
    config = {
        "event_scripts": {
            "enabled": True,
            "mappings": {
                "0": {
                    "mode": "get",
                    "script": "/nonexistent/script.txt"
                }
            },
            "on_error": "log_continue"
        }
    }
    
    registry = SessionRegistry()
    mgr = EventScriptManager(config, registry, log)
    
    sess = CPESession(serial="TEST001")
    info = {
        "events": [{"code": "0", "command_key": ""}],
        "device_id": {},
        "params": {}
    }
    
    try:
        mgr.trigger(sess, info)
        print("  ✓ Error handled gracefully (log_continue)\n")
        return True
    except Exception as e:
        print(f"  ✗ Unexpected exception: {e}\n")
        return False

def test_integration_with_example_scripts():
    """Test with actual example scripts."""
    print("="*60)
    print("Test 6: Integration with Example Scripts")
    print("="*60)
    
    # Check if example scripts exist
    script_files = [
        "prov/events/bootstrap.txt",
        "prov/events/boot.txt",
        "prov/events/periodic.txt"
    ]
    
    for script_file in script_files:
        if not os.path.exists(script_file):
            print(f"  ⚠ Script not found: {script_file}")
            continue
        
        config = {
            "event_scripts": {
                "enabled": True,
                "mappings": {
                    "0": {
                        "mode": "auto",
                        "script": script_file
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
        
        queued = len(sess.pending)
        print(f"  ✓ {script_file}: Queued {queued} RPC(s)")
    
    print("✓ Example scripts processed successfully\n")
    return True

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Event-Driven Script Execution - Test Suite")
    print("="*60 + "\n")
    
    tests = [
        test_event_script_manager_init,
        test_script_parsing,
        test_multi_level_fallback,
        test_mode_detection,
        test_error_handling,
        test_integration_with_example_scripts,
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
            failed += 1
    
    print("="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
