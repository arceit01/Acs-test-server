#!/bin/bash
# Demo script for multi-script sequential execution functionality

echo "=============================================="
echo "Demo: Multi-Script Sequential Execution"
echo "=============================================="
echo ""

echo "1. 功能特性"
echo "=============================================="
echo ""
cat << 'EOF'
✅ 順序執行：按配置順序依次執行每個腳本
✅ 失敗繼續：一個腳本失敗不影響後續腳本
✅ 數量限制：受 max_scripts_per_event 限制（預設 3）
✅ 混合模式：可混合 GET 和 SET 操作
✅ 完整日誌：記錄每個腳本的執行狀態
✅ 向後相容：單腳本配置仍正常運作
EOF
echo ""

echo "2. 配置格式比較"
echo "=============================================="
echo ""
echo "單腳本（向後相容）："
echo "-------------------"
cat << 'EOF'
{
  "event_scripts": {
    "mappings": {
      "0": {
        "mode": "set",
        "script": "prov/events/bootstrap.txt"
      }
    }
  }
}
EOF
echo ""

echo "多腳本（新功能）："
echo "-----------------"
cat << 'EOF'
{
  "event_scripts": {
    "max_scripts_per_event": 3,
    "mappings": {
      "0": {
        "scripts": [
          {
            "mode": "set",
            "script": "prov/events/bootstrap_base.txt",
            "description": "基礎配置"
          },
          {
            "mode": "set",
            "script": "prov/events/bootstrap_network.txt",
            "description": "網路配置"
          }
        ]
      }
    }
  }
}
EOF
echo ""

echo "3. 範例腳本檔案"
echo "=============================================="
echo ""
echo "基礎配置 (prov/events/bootstrap_base.txt):"
echo "-------------------------------------------"
head -10 prov/events/bootstrap_base.txt | sed 's/^/  /'
echo ""

echo "網路配置 (prov/events/bootstrap_network.txt):"
echo "----------------------------------------------"
head -10 prov/events/bootstrap_network.txt | sed 's/^/  /'
echo ""

echo "4. 典型使用場景"
echo "=============================================="
echo ""

echo "場景 1：分階段佈建"
echo "-------------------"
cat << 'EOF'
BOOTSTRAP 事件 → 執行 3 個階段：
  1. stage1_basic.txt (基礎配置)
  2. stage2_network.txt (網路配置)
  3. stage3_services.txt (服務配置)

優點：邏輯清晰，易於維護
EOF
echo ""

echo "場景 2：先查詢再配置"
echo "--------------------"
cat << 'EOF'
BOOTSTRAP 事件 → 執行 2 個腳本：
  1. check_current.txt (GET - 查詢目前設定)
  2. apply_new.txt (SET - 套用新配置)

優點：可驗證設備狀態再配置
EOF
echo ""

echo "場景 3：通用 + 客製"
echo "-------------------"
cat << 'EOF'
BOOTSTRAP 事件 → 執行 2 個腳本：
  1. common_config.txt (通用配置 - 所有設備)
  2. MOCK001_custom.txt (客製配置 - 特定設備)

優點：避免重複，易於管理
EOF
echo ""

echo "5. 執行流程示意"
echo "=============================================="
echo ""
cat << 'EOF'
CPE → Inform (Event 0 BOOTSTRAP)
  ↓
ACS 檢測多腳本配置
  ↓
執行 Script 1/3: bootstrap_base.txt (基礎配置)
  - 解析腳本
  - 排隊 5 個 SET RPC
  - 記錄：Executed successfully
  ↓
執行 Script 2/3: TESTDEV001_check.txt (檢查設定)
  - 解析腳本
  - 排隊 1 個 GET RPC (包含 6 個參數)
  - 記錄：Executed successfully
  ↓
執行 Script 3/3: TESTDEV001_custom.txt (客製配置)
  - 解析腳本
  - 排隊 3 個 SET RPC
  - 記錄：Executed successfully
  ↓
摘要：3 succeeded, 0 failed out of 3 scripts
  ↓
所有 RPC (9 個) 在隊列中，等待發送
EOF
echo ""

echo "6. 日誌輸出範例"
echo "=============================================="
echo ""
cat << 'EOF'
INFO: [TESTDEV001] Executing script 1/3: bootstrap_base.txt (基礎配置)
INFO: [TESTDEV001] Executed event script: bootstrap_base.txt 
      (event=0, mode=set, GET=0, SET=5)

INFO: [TESTDEV001] Executing script 2/3: TESTDEV001_check.txt (檢查設定)
INFO: [TESTDEV001] Executed event script: TESTDEV001_check.txt 
      (event=0, mode=get, GET=6, SET=0)

INFO: [TESTDEV001] Executing script 3/3: TESTDEV001_custom.txt (客製配置)
INFO: [TESTDEV001] Executed event script: TESTDEV001_custom.txt 
      (event=0, mode=set, GET=0, SET=3)

INFO: [TESTDEV001] Event 0: 3 succeeded, 0 failed out of 3 scripts
EOF
echo ""

echo "7. 測試驗證"
echo "=============================================="
echo ""
python3 test_multi_scripts.py 2>&1 | tail -15

echo ""
echo "8. 快速開始"
echo "=============================================="
echo ""
cat << 'EOF'
1. 使用多腳本配置：
   cp config_event_scripts_multi_example.json config.json

2. 檢視範例腳本：
   ls -l prov/events/bootstrap*.txt
   ls -l prov/devices/TESTDEV001*.txt

3. 啟動 ACS：
   python3 acs_server.py -c config.json

4. 連接測試設備：
   python3 mock_cpe.py --url http://127.0.0.1:7547/acs \
       --serial TESTDEV001 --bootstrap

5. 查看執行結果：
   acs> select 1
   acs[TESTDEV001]> hist
EOF
echo ""

echo "9. 文件資源"
echo "=============================================="
echo ""
cat << 'EOF'
• README.md → 快速參考
  Section: "多腳本順序執行"

• EVENT_SCRIPTS_GUIDE.md → 完整指南
  Section: "多腳本順序執行"

• config_event_scripts_multi_example.json → 完整配置範例

• test_multi_scripts.py → 單元測試

• CHANGELOG.md → v1.7.1 變更記錄
EOF
echo ""

echo "=============================================="
echo "Demo Complete!"
echo "=============================================="
echo ""
echo "多腳本功能可實現："
echo "  ✅ 分階段佈建（stage1 → stage2 → stage3）"
echo "  ✅ 先查詢再配置（GET → SET）"
echo "  ✅ 通用 + 客製（common → device-specific）"
echo ""
