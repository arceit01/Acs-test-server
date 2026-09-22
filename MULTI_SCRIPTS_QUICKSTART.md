# 多腳本順序執行 - 快速參考

## 🚀 快速開始（30 秒）

```bash
# 1. 使用多腳本配置
cp config_event_scripts_multi_example.json config.json

# 2. 啟動 ACS
python3 acs_server.py -c config.json

# 3. 連接測試設備
python3 mock_cpe.py --url http://127.0.0.1:7547/acs --serial TESTDEV001 --bootstrap

# 4. 查看執行結果
acs> select 1
acs[TESTDEV001]> hist
```

## 📝 配置格式

### 單腳本（舊格式，向後相容）

```json
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
```

### 多腳本（新格式，v1.7.1+）

```json
{
  "event_scripts": {
    "max_scripts_per_event": 3,
    "device_overrides": {
      "MOCK001": {
        "0": {
          "scripts": [
            {
              "mode": "set",
              "script": "prov/events/bootstrap.txt",
              "description": "通用配置"
            },
            {
              "mode": "set",
              "script": "prov/devices/MOCK001_custom.txt",
              "description": "客製配置"
            }
          ]
        }
      }
    }
  }
}
```

## 🎯 三大使用場景

### 場景 1：分階段佈建

```json
{
  "scripts": [
    {"mode": "set", "script": "stage1_basic.txt", "description": "階段 1"},
    {"mode": "set", "script": "stage2_network.txt", "description": "階段 2"},
    {"mode": "set", "script": "stage3_services.txt", "description": "階段 3"}
  ]
}
```

### 場景 2：先查詢再配置

```json
{
  "scripts": [
    {"mode": "get", "script": "check_current.txt", "description": "查詢"},
    {"mode": "set", "script": "apply_new.txt", "description": "配置"}
  ]
}
```

### 場景 3：通用 + 客製 ⭐

```json
{
  "scripts": [
    {"mode": "set", "script": "common.txt", "description": "通用"},
    {"mode": "set", "script": "device_specific.txt", "description": "客製"}
  ]
}
```

## ✅ 核心特性

| 特性 | 說明 |
|------|------|
| **順序執行** | 按配置順序依次執行 |
| **失敗繼續** | 一個失敗不影響後續 |
| **數量限制** | max_scripts_per_event（預設 3） |
| **混合模式** | GET/SET 可混用 |
| **獨立配置** | 每個腳本獨立設定 mode/script/description |
| **完整日誌** | 顯示進度和成功/失敗統計 |
| **向後相容** | 單腳本配置仍正常 |

## 📊 執行流程

```
CPE 發送 Inform (Event 0)
  ↓
ACS 偵測多腳本配置
  ↓
執行 Script 1/3 → 排隊 RPC
  ↓
執行 Script 2/3 → 排隊 RPC
  ↓
執行 Script 3/3 → 排隊 RPC
  ↓
摘要：3 succeeded, 0 failed
  ↓
所有 RPC 發送給 CPE
```

## 📋 日誌範例

```
INFO: [MOCK001] Executing script 1/3: bootstrap.txt (通用配置)
INFO: [MOCK001] Executed event script: bootstrap.txt (GET=0, SET=5)
INFO: [MOCK001] Executing script 2/3: MOCK001_custom.txt (客製配置)
INFO: [MOCK001] Executed event script: MOCK001_custom.txt (GET=0, SET=3)
INFO: [MOCK001] Event 0: 2 succeeded, 0 failed out of 2 scripts
```

## 🔧 配置選項

| 選項 | 預設值 | 說明 |
|------|--------|------|
| `max_scripts_per_event` | `3` | 每事件最大腳本數 |
| `description` | `""` | 腳本描述（顯示在日誌） |
| `mode` | `"auto"` | `get`/`set`/`auto` |

## 🧪 測試驗證

```bash
# 執行單元測試
python3 test_multi_scripts.py

# 查看演示
./demo_multi_scripts.sh
```

## 📚 完整文件

- **README.md** - Section: "多腳本順序執行"
- **EVENT_SCRIPTS_GUIDE.md** - Section: "多腳本順序執行"
- **config_event_scripts_multi_example.json** - 完整配置範例
- **CHANGELOG.md** - v1.7.1 變更記錄

## ⚠️ 注意事項

1. **數量建議**：每事件不超過 3 個腳本
2. **失敗處理**：預設繼續執行，不中斷
3. **向後相容**：舊配置完全不受影響
4. **腳本格式**：與 `open` 指令格式完全相同

## 💡 最佳實踐

- ✅ 使用 `description` 清楚說明每個腳本用途
- ✅ 按邏輯順序排列（如：先 GET 再 SET）
- ✅ 控制腳本數量，避免 session 時間過長
- ✅ 使用 Mock CPE 測試完整流程
- ✅ 查看日誌驗證每個腳本執行狀態

---

**版本**：v1.7.1  
**最後更新**：2026-09-21  
