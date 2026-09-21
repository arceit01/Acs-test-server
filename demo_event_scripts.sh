#!/bin/bash
# Demo script for event-driven script execution functionality

echo "=============================================="
echo "Demo: Event-Driven Script Execution"
echo "=============================================="
echo ""

# Show configuration
echo "1. Configuration Example"
echo "=============================================="
echo ""
echo "Enable event scripts in config.json:"
echo ""
cat << 'EOF'
{
  "event_scripts": {
    "enabled": true,
    "timing": "before_response",
    "mappings": {
      "0": {
        "mode": "set",
        "script": "prov/events/bootstrap.txt"
      },
      "1": {
        "mode": "get",
        "script": "prov/events/boot.txt"
      },
      "2": {
        "mode": "get",
        "script": "prov/events/periodic.txt"
      }
    },
    "device_overrides": {
      "MOCK001": {
        "0": {
          "mode": "set",
          "script": "prov/devices/MOCK001_bootstrap.txt"
        }
      }
    }
  }
}
EOF
echo ""

# Show example scripts
echo "=============================================="
echo "2. Example Event Scripts"
echo "=============================================="
echo ""

echo "Bootstrap Script (prov/events/bootstrap.txt):"
echo "----------------------------------------------"
head -15 prov/events/bootstrap.txt | sed 's/^/  /'
echo ""

echo "Boot Verification (prov/events/boot.txt):"
echo "----------------------------------------------"
head -15 prov/events/boot.txt | sed 's/^/  /'
echo ""

echo "Periodic Monitoring (prov/events/periodic.txt):"
echo "----------------------------------------------"
head -12 prov/events/periodic.txt | sed 's/^/  /'
echo ""

# Show event codes
echo "=============================================="
echo "3. TR-069 Event Codes"
echo "=============================================="
echo ""
cat << 'EOF'
Code  Event Name           When Triggered
----  -------------------  ----------------------------------
  0   BOOTSTRAP           First boot / Factory reset
  1   BOOT                Device reboot
  2   PERIODIC            Periodic inform
  4   VALUE CHANGE        Parameter value changed
  6   CONNECTION REQUEST  ACS-initiated connection
  7   TRANSFER COMPLETE   Firmware upgrade completed
EOF
echo ""

# Show multi-level fallback
echo "=============================================="
echo "4. Multi-Level Script Fallback"
echo "=============================================="
echo ""
cat << 'EOF'
Priority Order (highest to lowest):

1. device_overrides[SerialNumber][event_code]
   Example: prov/devices/MOCK001_bootstrap.txt

2. oui_overrides[OUI][event_code]
   Example: prov/oui/AABBCC_bootstrap.txt

3. product_class_overrides[ProductClass][event_code]
   Example: prov/products/Router_bootstrap.txt

4. mappings[event_code]
   Example: prov/events/bootstrap.txt

5. mappings[event_code].fallback (if main fails)
   Example: prov/events/minimal_bootstrap.txt
EOF
echo ""

# Show usage scenarios
echo "=============================================="
echo "5. Usage Scenarios"
echo "=============================================="
echo ""

echo "Scenario 1: Automatic Device Provisioning"
echo "-------------------------------------------"
cat << 'EOF'
CPE connects for first time → Event 0 BOOTSTRAP
  ↓
ACS executes bootstrap.txt
  ↓
SetParameterValues RPCs queued automatically
  ↓
Device configured without manual intervention
EOF
echo ""

echo "Scenario 2: Post-Reboot Health Check"
echo "--------------------------------------"
cat << 'EOF'
CPE reboots → Event 1 BOOT
  ↓
ACS executes boot.txt
  ↓
GetParameterValues RPC checks device status
  ↓
Results displayed in console (use 'hist')
EOF
echo ""

echo "Scenario 3: Regular Monitoring"
echo "-------------------------------"
cat << 'EOF'
CPE sends periodic inform → Event 2 PERIODIC
  ↓
ACS executes periodic.txt
  ↓
Monitoring data collected automatically
  ↓
Can be logged/analyzed for trends
EOF
echo ""

# Show how to test
echo "=============================================="
echo "6. How to Test"
echo "=============================================="
echo ""
cat << 'EOF'
Terminal 1: Start ACS with event scripts enabled
-------------------------------------------------
cp config_event_scripts_example.json config.json
python3 acs_server.py -c config.json

Terminal 2: Start Mock CPE with BOOTSTRAP event
------------------------------------------------
python3 mock_cpe.py --url http://127.0.0.1:7547/acs \
    --serial MOCK001 --bootstrap

Expected Output in ACS Console:
--------------------------------
[MOCK001] New CPE registered: events=[0 BOOTSTRAP] ...
[MOCK001] Executed event script: prov/events/bootstrap.txt 
          (event=0, queued=5 RPC)
[MOCK001] >> SetParameterValues ...
[MOCK001] >> SetParameterValues ...
...

Check Results:
--------------
acs> select 1
acs[MOCK001]> hist
  # View complete transaction history including script execution
EOF
echo ""

# Run unit tests
echo "=============================================="
echo "7. Run Unit Tests"
echo "=============================================="
echo ""
python3 test_event_scripts.py 2>&1 | tail -20

echo ""
echo "=============================================="
echo "8. Documentation"
echo "=============================================="
echo ""
cat << 'EOF'
Full documentation available in:

- README.md (Quick Reference)
  Section: "事件驅動自動化腳本"

- EVENT_SCRIPTS_GUIDE.md (Complete Guide)
  - Quick Start
  - Configuration Details
  - Script Format
  - Use Cases
  - Troubleshooting

- config_event_scripts_example.json (Configuration Example)

- prov/events/ (Example Scripts)
  - bootstrap.txt
  - boot.txt
  - periodic.txt
  - transfer_complete.txt
  - mixed_example.txt
EOF
echo ""

echo "=============================================="
echo "Demo Complete!"
echo "=============================================="
echo ""
echo "To get started:"
echo "  1. Copy config_event_scripts_example.json to config.json"
echo "  2. Customize scripts in prov/events/"
echo "  3. Start ACS: python3 acs_server.py -c config.json"
echo "  4. Connect CPE and watch automation in action!"
echo ""
