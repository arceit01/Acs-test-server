#!/bin/bash
# Demo script for the open --get functionality
# This script demonstrates the new batch GET feature

echo "=============================================="
echo "Demo: open --get functionality"
echo "=============================================="
echo ""

# Show the example GET files
echo "1. Example GET parameter files created:"
echo ""
echo "   prov/get_voice.txt:"
head -n 15 prov/get_voice.txt | sed 's/^/      /'
echo ""
echo "   prov/get_device_info.txt:"
head -n 15 prov/get_device_info.txt | sed 's/^/      /'
echo ""

# Show usage examples
echo "=============================================="
echo "2. Usage Examples:"
echo "=============================================="
echo ""
echo "   # Start ACS server"
echo "   python3 acs_server.py -c config.json"
echo ""
echo "   # In another terminal: Start mock CPE"
echo "   python3 mock_cpe.py --url http://127.0.0.1:7547/acs --serial MOCK001"
echo ""
echo "   # In console:"
echo "   acs> select 1"
echo "   acs[MOCK001]> open --get prov/get_voice.txt"
echo "   acs[MOCK001]> cr"
echo ""
echo "   # View response (automatically displayed)"
echo "   >> GetParameterValuesResponse:"
echo "   Device.Services.VoiceService.1.VoiceProfile.1.Line.1.SIP.AuthUserName = value [xsd:string]"
echo "   ..."
echo ""

# Show comparison
echo "=============================================="
echo "3. Feature Comparison:"
echo "=============================================="
echo ""
echo "   SET mode (default):"
echo "     - Command: open prov/voice.txt"
echo "     - File format: path=value[:type]"
echo "     - Creates: N separate SetParameterValues RPCs (one per parameter)"
echo "     - Use case: Batch configuration updates"
echo ""
echo "   GET mode (--get):"
echo "     - Command: open --get prov/voice.txt"
echo "     - File format: path (or path=value, value ignored)"
echo "     - Creates: Single GetParameterValues RPC (all parameters)"
echo "     - Use case: Batch parameter queries"
echo ""

# Show file format compatibility
echo "=============================================="
echo "4. File Format Compatibility:"
echo "=============================================="
echo ""
echo "   The same file can be used for both GET and SET!"
echo ""
echo "   File content:"
echo "     Device.WiFi.Radio.1.Enable=true:boolean"
echo "     Device.WiFi.Radio.1.Channel=6:uint"
echo ""
echo "   Usage:"
echo "     open --get wifi.txt    → Gets current values (ignores =value)"
echo "     open wifi.txt          → Sets new values"
echo ""

echo "=============================================="
echo "5. Run unit tests:"
echo "=============================================="
echo ""
python3 test_open_get.py

echo ""
echo "=============================================="
echo "Demo complete!"
echo "=============================================="
