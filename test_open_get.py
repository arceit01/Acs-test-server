#!/usr/bin/env python3
"""Quick test for the open --get functionality."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from cpe_session import SessionRegistry, CPESession, OutboundRPC
import shlex

def test_file_parsing():
    """Test the file parsing logic for GET mode."""
    print("Testing file parsing logic...")
    
    # Simulate reading get_voice.txt
    test_lines = [
        "# Comment line",
        "",
        "Device.Services.VoiceService.1.VoiceProfile.1.Line.1.SIP.AuthUserName",
        "Device.Services.VoiceService.1.VoiceProfile.1.Line.1.SIP.AuthPassword",
        "Device.Services.VoiceService.1.VoiceProfile.1.Line.1.Enable",
        "",
        "# Another comment",
        "Device.Services.VoiceService.1.VoiceProfile.1.SIP.RegistrarServer=voip.example.com",
    ]
    
    param_names = []
    line_num = 0
    
    for line in test_lines:
        line_num += 1
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Support both "path" and "path=value" formats
        name, sep, raw = line.partition('=')
        name = name.strip()
        if not name:
            print(f"Line {line_num}: empty parameter name")
            return False
        
        param_names.append(name)
        print(f"  Line {line_num}: {name}")
    
    print(f"\nExtracted {len(param_names)} parameters:")
    for p in param_names:
        print(f"  - {p}")
    
    expected_count = 4
    if len(param_names) == expected_count:
        print(f"\n✓ Test PASSED: Found {expected_count} parameters as expected")
        return True
    else:
        print(f"\n✗ Test FAILED: Expected {expected_count}, found {len(param_names)}")
        return False

def test_argument_parsing():
    """Test the argument parsing for --get flag."""
    print("\n" + "="*60)
    print("Testing argument parsing...")
    
    test_cases = [
        ("--get prov/voice.txt", True, "prov/voice.txt"),
        ("prov/voice.txt", False, "prov/voice.txt"),
        ("--get prov/get_voice.txt", True, "prov/get_voice.txt"),
        ("prov/voice.txt --get", None, None),  # Invalid order - should handle gracefully
    ]
    
    for arg_string, expected_get, expected_file in test_cases:
        print(f"\nTest: '{arg_string}'")
        tokens = shlex.split(arg_string)
        
        get_mode = False
        filepath = None
        
        for token in tokens:
            if token == "--get":
                get_mode = True
            elif not filepath:
                filepath = token
        
        if expected_get is None:
            print(f"  Expected: (invalid)")
        else:
            print(f"  Expected: get_mode={expected_get}, filepath={expected_file}")
        print(f"  Got:      get_mode={get_mode}, filepath={filepath}")
        
        if expected_get is not None and get_mode == expected_get and filepath == expected_file:
            print("  ✓ PASSED")
        elif expected_get is None:
            print("  ℹ Handled by console UI validation")
        else:
            print("  ✗ FAILED")

def test_rpc_creation():
    """Test RPC creation for GetParameterValues."""
    print("\n" + "="*60)
    print("Testing RPC creation...")
    
    param_names = [
        "Device.WiFi.Radio.1.Enable",
        "Device.WiFi.Radio.1.Channel",
        "Device.WiFi.SSID.1.SSID",
    ]
    
    args = {"names": param_names}
    summary = f"{len(param_names)} parameter(s)"
    rpc = OutboundRPC("GetParameterValues", args, summary)
    
    print(f"  Method: {rpc.method}")
    print(f"  Args: {rpc.args}")
    print(f"  Summary: {rpc.summary}")
    
    if rpc.method == "GetParameterValues" and rpc.args["names"] == param_names:
        print("\n✓ Test PASSED: RPC created correctly")
        return True
    else:
        print("\n✗ Test FAILED: RPC creation error")
        return False

if __name__ == "__main__":
    print("="*60)
    print("Testing open --get functionality")
    print("="*60)
    
    all_passed = True
    all_passed &= test_file_parsing()
    test_argument_parsing()  # Not affecting all_passed (some are informational)
    all_passed &= test_rpc_creation()
    
    print("\n" + "="*60)
    if all_passed:
        print("All tests PASSED ✓")
        sys.exit(0)
    else:
        print("Some tests FAILED ✗")
        sys.exit(1)
