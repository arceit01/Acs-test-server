# 事件驅動自動化腳本完整指南

## 目錄

- [簡介](#簡介)
- [快速開始](#快速開始)
- [配置詳解](#配置詳解)
- [腳本格式](#腳本格式)
- [事件代碼](#事件代碼)
- [使用案例](#使用案例)
- [多層級回退機制](#多層級回退機制)
- [執行時機與流程](#執行時機與流程)
- [錯誤處理](#錯誤處理)
- [最佳實踐](#最佳實踐)
- [故障排除](#故障排除)
- [技術細節](#技術細節)

---

## 簡介

事件驅動自動化腳本系統讓 ACS 能夠根據 CPE 發送的 TR-069 Inform 事件自動執行預定義的操作，實現：

- **零人工介入的自動化佈建**：新設備連線時自動配置
- **智能監控**：定期收集關鍵指標
- **故障診斷**：設備重啟或異常時自動檢查
- **韌體升級驗證**：升級完成後自動驗證
- **設備特定配置**：針對不同設備/廠商/型號執行不同腳本

### 核心特性

✅ 支援所有 TR-069 事件代碼（0-31）  
✅ 多層級腳本回退（Serial → OUI → ProductClass → 預設）  
✅ GET/SET/AUTO 三種操作模式  
✅ 可配置執行時機（InformResponse 前/後）  
✅ 完整的錯誤處理和日誌記錄  
✅ 與現有 `open` 指令格式完全相容  

---

## 快速開始

### 1. 啟用功能

編輯 `config.json`：

```json
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
      }
    }
  }
}
```

### 2. 建立腳本

**BOOTSTRAP 自動佈建** (`prov/events/bootstrap.txt`)：

```
#MODE=set
Device.ManagementServer.PeriodicInformEnable=true:boolean
Device.ManagementServer.PeriodicInformInterval=300:uint
Device.Time.NTPServer1=time.google.com
```

**BOOT 健康檢查** (`prov/events/boot.txt`)：

```
#MODE=get
Device.DeviceInfo.UpTime
Device.DeviceInfo.SoftwareVersion
Device.IP.Interface.1.Status
```

### 3. 測試

```bash
# 啟動 ACS
python3 acs_server.py -c config.json

# 啟動 Mock CPE（會觸發 BOOTSTRAP）
python3 mock_cpe.py --url http://127.0.0.1:7547/acs --serial MOCK001 --bootstrap
```

查看 console 輸出，應該會看到：

```
[MOCK001] Executed event script: prov/events/bootstrap.txt (event=0, queued=3 RPC)
```

---

## 配置詳解

### 完整配置結構

```json
{
  "event_scripts": {
    "enabled": false,                    // 總開關
    "timing": "before_response",         // 執行時機
    "mappings": {                        // 預設事件映射
      "0": {                            // 事件代碼
        "mode": "set",                  // 操作模式
        "script": "path/to/script.txt", // 腳本路徑
        "fallback": "path/to/backup.txt" // 備用腳本（可選）
      }
    },
    "device_overrides": {                // 設備特定（Serial Number）
      "MOCK001": {
        "0": {
          "mode": "set",
          "script": "prov/devices/MOCK001_bootstrap.txt"
        }
      }
    },
    "oui_overrides": {                   // OUI 特定（製造商）
      "AABBCC": {
        "0": {
          "mode": "set",
          "script": "prov/oui/AABBCC_bootstrap.txt"
        }
      }
    },
    "product_class_overrides": {         // ProductClass 特定（型號）
      "MockCPE": {
        "1": {
          "mode": "get",
          "script": "prov/products/MockCPE_boot.txt"
        }
      }
    },
    "on_error": "log_continue",          // 錯誤處理策略
    "max_scripts_per_event": 1,          // 每事件最大腳本數
    "log_execution": true                // 是否記錄執行日誌
  }
}
```

### 配置選項說明

#### enabled
- **類型**：`boolean`
- **預設值**：`false`
- **說明**：功能總開關。預設關閉以保持向後相容性。

#### timing
- **類型**：`string`
- **預設值**：`"before_response"`
- **選項**：
  - `"before_response"`：在 InformResponse 發送前執行（推薦）
  - `"after_response"`：在 InformResponse 發送後執行
- **說明**：決定腳本 RPC 何時排隊。`before_response` 可確保 RPC 在同一 session 中發送。

#### mode
- **類型**：`string`
- **預設值**：`"auto"`
- **選項**：
  - `"get"`：僅執行 GET 操作
  - `"set"`：僅執行 SET 操作
  - `"auto"`：根據參數格式自動判斷（有 `=` 為 SET，否則為 GET）
- **說明**：可在配置中設定，也可在腳本中用 `#MODE=` 覆蓋。

#### on_error
- **類型**：`string`
- **預設值**：`"log_continue"`
- **選項**：
  - `"log_continue"`：記錄錯誤並繼續（推薦）
  - `"use_fallback"`：嘗試執行 fallback 腳本
  - `"abort_session"`：中斷 session（謹慎使用）
- **說明**：腳本執行失敗時的行為。

#### max_scripts_per_event
- **類型**：`integer`
- **預設值**：`1`
- **說明**：每個事件最多執行的腳本數量。防止腳本遞迴或過載。

#### log_execution
- **類型**：`boolean`
- **預設值**：`true`
- **說明**：是否將腳本執行記錄到 Session history。

---

## 腳本格式

### 基本格式

腳本檔案是純文字檔，每行一個參數操作：

```
# 註解以 # 開頭
#MODE=get|set|auto

# GET 操作（無 '='）
Device.DeviceInfo.SoftwareVersion

# SET 操作（有 '='）
Device.ManagementServer.PeriodicInformInterval=300:uint

# 空行會被忽略
```

### MODE 指令

在腳本開頭使用 `#MODE=` 指定操作模式：

```
#MODE=get
# 接下來的所有參數都會被當作 GET 操作
Device.DeviceInfo.UpTime
Device.IP.Interface.1.Status
```

```
#MODE=set
# 接下來的所有參數都會被當作 SET 操作
Device.ManagementServer.PeriodicInformEnable=true:boolean
Device.Time.NTPServer1=time.google.com
```

```
#MODE=auto
# 自動偵測（有 '=' 為 SET，否則為 GET）
Device.DeviceInfo.UpTime                              # GET
Device.ManagementServer.PeriodicInformInterval=600:uint  # SET
```

### 型別標記

SET 操作支援明確指定型別（使用 `:type` 後綴）：

```
Device.ManagementServer.PeriodicInformEnable=true:boolean
Device.ManagementServer.PeriodicInformInterval=300:uint
Device.Time.NTPServer1=time.google.com:string
Device.WiFi.Radio.1.TxPower=80:int
```

支援的型別別名：
- `bool` / `boolean`
- `int` / `integer`
- `uint` / `unsignedint`
- `string` / `str`
- `double` / `float`
- `datetime` / `date`

### 註解規則

- 以 `#` 開頭的行為註解（除了 `#MODE=`）
- 空行會被忽略
- 行內註解不支援（整行都是註解或參數）

### 完整範例

```
# BOOTSTRAP 初始化腳本
# 此腳本在 CPE 首次連線或恢復出廠設置時執行

#MODE=set

# 啟用定期 Inform
Device.ManagementServer.PeriodicInformEnable=true:boolean
Device.ManagementServer.PeriodicInformInterval=300:uint

# 設定 NTP 伺服器
Device.Time.Enable=true:boolean
Device.Time.NTPServer1=time.google.com
Device.Time.NTPServer2=time.nist.gov

# 設定裝置資訊
Device.DeviceInfo.Description=Auto-provisioned by ACS
```

---

## 事件代碼

### 標準 TR-069 事件

| 代碼 | 事件名稱 | 觸發時機 | 典型用途 |
|------|---------|---------|---------|
| `0` | BOOTSTRAP | 首次啟動 / 恢復出廠設置 | 初始化佈建、基本配置 |
| `1` | BOOT | 設備重啟（電源重啟） | 重啟後驗證、健康檢查 |
| `2` | PERIODIC | 週期性 Inform | 定期監控、數據收集 |
| `3` | SCHEDULED | 排程的 Inform | 定時任務 |
| `4` | VALUE CHANGE | 參數值變更通知 | 配置變更追蹤 |
| `5` | KICKED | 被其他 ACS 踢下線 | 衝突處理 |
| `6` | CONNECTION REQUEST | ACS 觸發的連接 | 主動管理指令 |
| `7` | TRANSFER COMPLETE | 檔案傳輸完成 | 韌體升級驗證 |
| `8` | DIAGNOSTICS COMPLETE | 診斷測試完成 | 診斷結果處理 |
| `9` | REQUEST DOWNLOAD | CPE 請求下載 | 自動更新處理 |
| `10` | AUTONOMOUS TRANSFER COMPLETE | 自主傳輸完成 | 自動更新驗證 |

### 廠商自定義事件

部分廠商（如 Arcadyan）可能使用自定義事件代碼（11-31）。可在配置中映射這些事件到對應腳本。

### 組合事件

CPE 可能在一個 Inform 中發送多個事件。ACS 會依序處理每個事件，但受 `max_scripts_per_event` 限制。

---

## 使用案例

### 案例 1：新設備自動佈建

**需求**：新設備首次連線時自動配置管理參數。

**配置**：
```json
{
  "event_scripts": {
    "enabled": true,
    "mappings": {
      "0": {
        "mode": "set",
        "script": "prov/events/bootstrap.txt"
      }
    }
  }
}
```

**腳本** (`prov/events/bootstrap.txt`)：
```
#MODE=set
Device.ManagementServer.PeriodicInformEnable=true:boolean
Device.ManagementServer.PeriodicInformInterval=300:uint
Device.Time.Enable=true:boolean
Device.Time.NTPServer1=time.google.com
```

**結果**：設備連線時自動配置，無需手動介入。

### 案例 2：重啟後健康檢查

**需求**：設備重啟後自動驗證關鍵參數。

**配置**：
```json
{
  "event_scripts": {
    "enabled": true,
    "mappings": {
      "1": {
        "mode": "get",
        "script": "prov/events/boot_verify.txt"
      }
    }
  }
}
```

**腳本** (`prov/events/boot_verify.txt`)：
```
#MODE=get
Device.DeviceInfo.UpTime
Device.DeviceInfo.SoftwareVersion
Device.IP.Interface.1.Status
Device.IP.Interface.1.IPv4Address.1.IPAddress
Device.ManagementServer.ConnectionRequestURL
```

**結果**：ACS 自動收集設備狀態，可在 console 用 `hist` 查看。

### 案例 3：定期監控

**需求**：定期收集設備運行指標。

**配置**：
```json
{
  "event_scripts": {
    "enabled": true,
    "mappings": {
      "2": {
        "mode": "get",
        "script": "prov/events/periodic_monitor.txt"
      }
    }
  }
}
```

**腳本** (`prov/events/periodic_monitor.txt`)：
```
#MODE=get
Device.DeviceInfo.UpTime
Device.DeviceInfo.MemoryStatus.Total
Device.DeviceInfo.MemoryStatus.Free
Device.IP.Interface.1.Stats.BytesSent
Device.IP.Interface.1.Stats.BytesReceived
```

**結果**：每次週期性 Inform 自動收集監控數據。

### 案例 4：韌體升級後驗證

**需求**：韌體升級完成後驗證新版本。

**配置**：
```json
{
  "event_scripts": {
    "enabled": true,
    "mappings": {
      "7": {
        "mode": "get",
        "script": "prov/events/fw_verify.txt"
      }
    }
  }
}
```

**腳本** (`prov/events/fw_verify.txt`)：
```
#MODE=get
Device.DeviceInfo.SoftwareVersion
Device.DeviceInfo.HardwareVersion
Device.DeviceInfo.UpTime
```

**結果**：升級完成後自動查詢新版本號。

### 案例 5：設備特定配置

**需求**：測試設備使用不同的配置。

**配置**：
```json
{
  "event_scripts": {
    "enabled": true,
    "mappings": {
      "0": {
        "mode": "set",
        "script": "prov/events/bootstrap.txt"
      }
    },
    "device_overrides": {
      "TESTDEV001": {
        "0": {
          "mode": "set",
          "script": "prov/devices/TESTDEV001_bootstrap.txt"
        }
      }
    }
  }
}
```

**腳本** (`prov/devices/TESTDEV001_bootstrap.txt`)：
```
#MODE=set
# 測試設備使用更短的 Inform 間隔
Device.ManagementServer.PeriodicInformInterval=60:uint
Device.DeviceInfo.Description=Test Device - Fast Polling
```

**結果**：TESTDEV001 使用特定配置，其他設備使用預設配置。

---

## 多腳本順序執行

從 v1.7.1 開始，支援在同一事件中順序執行多個腳本。

### 功能特性

- ✅ **順序執行**：按配置順序依次執行每個腳本
- ✅ **失敗繼續**：一個腳本失敗不影響後續腳本執行
- ✅ **數量限制**：受 `max_scripts_per_event` 限制（預設 3）
- ✅ **混合模式**：可混合 GET 和 SET 操作
- ✅ **獨立配置**：每個腳本可獨立設定 mode、script、description
- ✅ **完整日誌**：記錄每個腳本的執行狀態

### 配置格式

#### 單腳本（向後相容）

```json
{
  "event_scripts": {
    "mappings": {
      "0": {
        "mode": "set",
        "script": "prov/events/bootstrap.txt",
        "fallback": "prov/events/minimal.txt"
      }
    }
  }
}
```

#### 多腳本（新格式）

```json
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
    },
    "device_overrides": {
      "TESTDEV001": {
        "0": {
          "scripts": [
            {
              "mode": "set",
              "script": "prov/events/bootstrap.txt",
              "description": "通用配置"
            },
            {
              "mode": "get",
              "script": "prov/devices/TESTDEV001_check.txt",
              "description": "檢查目前設定"
            },
            {
              "mode": "set",
              "script": "prov/devices/TESTDEV001_custom.txt",
              "description": "客製配置"
            }
          ]
        }
      }
    }
  }
}
```

### 執行流程

```
CPE 發送 Inform (Event 0 BOOTSTRAP)
  ↓
ACS 檢測到多腳本配置 (scripts: [...])
  ↓
應用 max_scripts_per_event 限制
  ↓
執行 Script 1: bootstrap_base.txt
  - 記錄：[SERIAL] Executing script 1/3: bootstrap_base.txt (基礎配置)
  - 解析腳本，排隊 RPC
  - 記錄：[SERIAL] Executed event script: ... (mode=set, GET=0, SET=5)
  ↓
執行 Script 2: TESTDEV001_check.txt
  - 記錄：[SERIAL] Executing script 2/3: TESTDEV001_check.txt (檢查目前設定)
  - 解析腳本，排隊 RPC
  - 記錄：[SERIAL] Executed event script: ... (mode=get, GET=6, SET=0)
  ↓
執行 Script 3: TESTDEV001_custom.txt
  - 記錄：[SERIAL] Executing script 3/3: TESTDEV001_custom.txt (客製配置)
  - 解析腳本，排隊 RPC
  - 記錄：[SERIAL] Executed event script: ... (mode=set, GET=0, SET=3)
  ↓
最終摘要：[SERIAL] Event 0: 3 succeeded, 0 failed out of 3 scripts
  ↓
所有 RPC 在隊列中，等待發送
```

### 典型使用場景

#### 場景 1：分階段佈建

**需求**：BOOTSTRAP 時分三階段配置設備

**配置**：
```json
{
  "event_scripts": {
    "mappings": {
      "0": {
        "scripts": [
          {
            "mode": "set",
            "script": "prov/events/stage1_basic.txt",
            "description": "階段 1：基礎配置"
          },
          {
            "mode": "set",
            "script": "prov/events/stage2_network.txt",
            "description": "階段 2：網路配置"
          },
          {
            "mode": "set",
            "script": "prov/events/stage3_services.txt",
            "description": "階段 3：服務配置"
          }
        ]
      }
    }
  }
}
```

**結果**：
- 設備依序接收三批配置
- 即使某階段失敗，其他階段仍會執行
- 日誌清楚顯示每階段的執行狀態

#### 場景 2：先查詢再配置

**需求**：配置前先查詢目前設定，用於驗證或決策

**配置**：
```json
{
  "event_scripts": {
    "device_overrides": {
      "TESTDEV001": {
        "0": {
          "scripts": [
            {
              "mode": "get",
              "script": "prov/devices/TESTDEV001_check.txt",
              "description": "查詢目前配置"
            },
            {
              "mode": "set",
              "script": "prov/devices/TESTDEV001_update.txt",
              "description": "套用新配置"
            }
          ]
        }
      }
    }
  }
}
```

**結果**：
- 先執行 GET 取得目前值
- 再執行 SET 套用新配置
- Console 可用 `hist` 查看查詢結果

#### 場景 3：通用 + 客製

**需求**：所有設備套用通用配置，特定設備追加客製配置

**配置**：
```json
{
  "event_scripts": {
    "device_overrides": {
      "MOCK001": {
        "0": {
          "scripts": [
            {
              "mode": "set",
              "script": "prov/events/bootstrap.txt",
              "description": "通用配置（所有設備適用）"
            },
            {
              "mode": "set",
              "script": "prov/devices/MOCK001_custom.txt",
              "description": "MOCK001 客製配置"
            }
          ]
        }
      }
    }
  }
}
```

**結果**：
- MOCK001 先套用通用配置
- 再套用設備特定配置
- 其他設備只執行通用配置（如果在 `mappings` 中定義）

### 失敗處理

#### 失敗繼續模式（預設）

```
Script 1: 成功 → 排隊 5 個 SET RPC
  ↓
Script 2: 失敗（檔案不存在）→ 記錄 WARNING
  ↓
Script 3: 成功 → 排隊 3 個 SET RPC
  ↓
最終：2 succeeded, 1 failed out of 3 scripts
```

**日誌範例**：
```
INFO: [MOCK001] Executing script 1/3: stage1.txt (階段 1)
INFO: [MOCK001] Executed event script: stage1.txt (queued=5 RPC)
INFO: [MOCK001] Executing script 2/3: stage2.txt (階段 2)
WARNING: [MOCK001] Cannot open script 'stage2.txt': No such file or directory
INFO: [MOCK001] Executing script 3/3: stage3.txt (階段 3)
INFO: [MOCK001] Executed event script: stage3.txt (queued=3 RPC)
INFO: [MOCK001] Event 0: 2 succeeded, 1 failed out of 3 scripts
```

#### 空腳本列表

如果 `scripts: []` 為空陣列：
```
WARNING: [MOCK001] Event 0 has empty scripts list
```

#### 超過數量限制

如果配置 5 個腳本但 `max_scripts_per_event: 3`：
```
WARNING: [MOCK001] Event 0 has 5 scripts, limiting to first 3
INFO: [MOCK001] Executing script 1/3: ...
INFO: [MOCK001] Executing script 2/3: ...
INFO: [MOCK001] Executing script 3/3: ...
# Script 4 和 5 不執行
```

### 配置選項

| 選項 | 說明 | 預設值 | 備註 |
|------|------|--------|------|
| `max_scripts_per_event` | 每事件最大腳本數 | `3` | v1.7.1 從 1 改為 3 |
| `description` | 腳本描述 | `""` | 顯示在日誌中，可選 |
| `mode` | 腳本模式 | `"auto"` | 可在腳本中用 `#MODE=` 覆蓋 |

### 最佳實踐

1. **合理的數量**：建議每事件不超過 3 個腳本，避免 session 時間過長
2. **清晰的描述**：使用 `description` 欄位說明每個腳本的用途
3. **邏輯順序**：按依賴關係排列（如：先 GET 再 SET）
4. **錯誤容忍**：考慮某些腳本可能失敗的情況
5. **測試驗證**：使用 Mock CPE 測試完整流程

### 完整範例

參見 `config_event_scripts_multi_example.json` 完整配置示範。

---

## 多層級回退機制

### 查找順序

腳本查找按以下優先順序進行：

```
1. device_overrides[SerialNumber][event_code]     ← 最高優先權
2. oui_overrides[OUI][event_code]
3. product_class_overrides[ProductClass][event_code]
4. mappings[event_code]
5. mappings[event_code].fallback                   ← 僅在主腳本失敗時
```

### 範例配置

```json
{
  "event_scripts": {
    "enabled": true,
    "mappings": {
      "0": {
        "mode": "set",
        "script": "prov/events/default_bootstrap.txt",
        "fallback": "prov/events/minimal_bootstrap.txt"
      }
    },
    "device_overrides": {
      "SPECIAL001": {
        "0": {
          "mode": "set",
          "script": "prov/devices/SPECIAL001_bootstrap.txt"
        }
      }
    },
    "oui_overrides": {
      "AABBCC": {
        "0": {
          "mode": "set",
          "script": "prov/oui/AABBCC_bootstrap.txt"
        }
      }
    },
    "product_class_overrides": {
      "HomeRouter": {
        "0": {
          "mode": "set",
          "script": "prov/products/HomeRouter_bootstrap.txt"
        }
      }
    }
  }
}
```

### 實際行為

| CPE | SerialNumber | OUI | ProductClass | 使用腳本 |
|-----|-------------|-----|--------------|---------|
| CPE-A | SPECIAL001 | AABBCC | HomeRouter | `SPECIAL001_bootstrap.txt` |
| CPE-B | NORMAL002 | AABBCC | HomeRouter | `AABBCC_bootstrap.txt` |
| CPE-C | NORMAL003 | XXYYZZ | HomeRouter | `HomeRouter_bootstrap.txt` |
| CPE-D | NORMAL004 | XXYYZZ | Gateway | `default_bootstrap.txt` |

---

## 執行時機與流程

### CWMP Session 流程

```
CPE                           ACS
 |                             |
 |-------- Inform ----------->|
 |                             | 1. 解析 Inform（提取 events）
 |                             | 2. 創建/更新 Session
 |                             | 3. 執行自動佈建 CR（如果是 BOOTSTRAP）
 |                             |
 |                             | === timing: before_response ===
 |                             | 4. 查找事件腳本
 |                             | 5. 解析腳本並排隊 RPC
 |                             | ================================
 |                             |
 |<--- InformResponse --------| 6. 發送 InformResponse
 |                             |
 |                             | === timing: after_response ===
 |                             | (如果設定為 after_response，此時執行)
 |                             | ================================
 |                             |
 |---- 空 POST（輪詢）------->| 7. CPE 輪詢 RPC
 |                             | 8. 從隊列取出 RPC
 |<--- RPC（腳本排隊）-------| 9. 發送腳本中的 RPC
 |                             |
 |---- Response -------------->| 10. 接收響應
 |                             | 11. 繼續 session 或結束
```

### before_response vs after_response

#### before_response（推薦）

**優點**：
- RPC 在同一 session 中發送
- 響應更快
- 邏輯清晰

**缺點**：
- 如果腳本處理時間長，會延遲 InformResponse

#### after_response

**優點**：
- InformResponse 更快
- 腳本處理不阻塞

**缺點**：
- RPC 需要等待 CPE 下一次輪詢
- 時序不如 before_response 明確

---

## 錯誤處理

### 錯誤類型

1. **腳本檔案不存在**
   - 記錄 WARNING 日誌
   - 返回 False（失敗）

2. **腳本格式錯誤**
   - 空參數名：跳過該行
   - 無效 MODE：忽略，使用配置中的 mode

3. **腳本無有效操作**
   - 記錄 WARNING 日誌
   - 返回 False（失敗）

4. **RPC 執行失敗**
   - CPE 回應 Fault：記錄到 history
   - 觸發自動診斷（如果啟用）

### on_error 策略

#### log_continue（推薦）

```json
{
  "event_scripts": {
    "on_error": "log_continue"
  }
}
```

**行為**：
- 記錄錯誤到日誌
- 繼續執行 CWMP session
- 不影響其他操作

**適用場景**：生產環境（穩定性優先）

#### use_fallback

```json
{
  "event_scripts": {
    "mappings": {
      "0": {
        "mode": "set",
        "script": "prov/events/bootstrap.txt",
        "fallback": "prov/events/minimal_bootstrap.txt"
      }
    },
    "on_error": "use_fallback"
  }
}
```

**行為**：
- 主腳本失敗時嘗試 fallback 腳本
- fallback 也失敗則記錄錯誤
- 繼續執行 CWMP session

**適用場景**：有備用配置的環境

#### abort_session

```json
{
  "event_scripts": {
    "on_error": "abort_session"
  }
}
```

**行為**：
- 腳本失敗時拋出異常
- 不發送 InformResponse
- CPE 會重試 Inform

**適用場景**：測試環境（快速發現問題）

**⚠️ 警告**：慎用於生產環境，可能導致 CPE 無限重試。

---

## 最佳實踐

### 1. 腳本組織

```
prov/
├── events/              # 通用事件腳本
│   ├── bootstrap.txt
│   ├── boot.txt
│   └── periodic.txt
├── devices/             # 設備特定
│   ├── DEV001_bootstrap.txt
│   └── DEV001_boot.txt
├── oui/                 # 廠商特定
│   └── AABBCC_bootstrap.txt
└── products/            # 型號特定
    └── Router5G_boot.txt
```

### 2. 腳本命名

使用清晰的命名規範：

```
{entity}_{event}.txt

範例：
- bootstrap.txt          (預設)
- MOCK001_bootstrap.txt  (設備特定)
- AABBCC_periodic.txt    (OUI 特定)
- Router5G_boot.txt      (型號特定)
```

### 3. 註解習慣

```
# === 檔案標頭 ===
# Script: Bootstrap Initial Provisioning
# Event: 0 BOOTSTRAP
# Mode: SET
# Author: Admin
# Date: 2026-09-21
# Description: Configure basic management parameters

#MODE=set

# === Management Server ===
Device.ManagementServer.PeriodicInformEnable=true:boolean
Device.ManagementServer.PeriodicInformInterval=300:uint

# === Time Configuration ===
Device.Time.Enable=true:boolean
Device.Time.NTPServer1=time.google.com
```

### 4. 版本控制

將腳本檔案加入 Git：

```bash
git add prov/events/*.txt
git add prov/devices/*.txt
git commit -m "Add event-driven provisioning scripts"
```

### 5. 測試流程

1. **在測試環境驗證**
   ```json
   {
     "event_scripts": {
       "enabled": true,
       "log_execution": true,
       "on_error": "log_continue"
     }
   }
   ```

2. **使用 Mock CPE 測試**
   ```bash
   python3 mock_cpe.py --url http://127.0.0.1:7547/acs \
       --serial TESTDEV --bootstrap
   ```

3. **檢查日誌**
   ```bash
   grep "event script" acs.log
   ```

4. **驗證 RPC**
   - Console 使用 `hist TESTDEV`
   - 確認 RPC 正確執行

### 6. 逐步部署

1. 單一設備測試（`device_overrides`）
2. 小批量測試（OUI 或 ProductClass）
3. 全面部署（`mappings`）

### 7. 監控與日誌

- 啟用 `log_execution: true`
- 定期檢查 `sess.history`
- 關注 WARNING 和 ERROR 日誌

---

## 故障排除

### 問題 1：腳本未執行

**症狀**：CPE 連線但腳本沒有執行。

**檢查清單**：
1. ✅ `enabled: true`？
2. ✅ 事件代碼正確？（用 `hist` 查看 Inform events）
3. ✅ 腳本路徑正確？（檔案存在？）
4. ✅ 腳本有內容？（不是空檔案）

**調試**：
```bash
# 檢查配置
cat config.json | grep -A 20 event_scripts

# 檢查腳本
cat prov/events/bootstrap.txt

# 檢查日誌
grep "event script" acs.log
```

### 問題 2：RPC 未發送

**症狀**：腳本執行了但 RPC 沒有發送。

**可能原因**：
1. 腳本格式錯誤（參數名為空）
2. MODE 設定錯誤（GET 模式但參數有 `=`）
3. `timing: after_response` 但 CPE 沒有輪詢

**調試**：
```bash
# 查看 session history
acs> select DEVICE
acs[DEVICE]> hist

# 查看待發送隊列
acs[DEVICE]> show
```

### 問題 3：TYPE 錯誤

**症狀**：CPE 回應 Fault 9003（Invalid arguments）。

**解決方法**：
1. 加上明確型別標記
   ```
   Device.ManagementServer.PeriodicInformEnable=true:boolean
   ```

2. 先 GET 參數讓 ACS 學習型別
   ```
   #MODE=get
   Device.ManagementServer.PeriodicInformEnable
   ```

3. 參考自動診斷結果

### 問題 4：腳本查找錯誤

**症狀**：優先順序不符預期。

**檢查清單**：
1. ✅ SerialNumber 正確？（區分大小寫）
2. ✅ OUI 正確？（6 個字元）
3. ✅ ProductClass 正確？

**調試**：
```bash
# 查看設備資訊
acs> select DEVICE
acs[DEVICE]> info

# 檢查配置
cat config.json | jq '.event_scripts.device_overrides'
```

### 問題 5：性能問題

**症狀**：Session 時間過長。

**解決方法**：
1. 減少腳本中的參數數量
2. 使用 GET 模式（單一 RPC）而非 SET（多個 RPC）
3. 設定 `max_scripts_per_event: 1`
4. 考慮使用 `timing: after_response`

---

## 技術細節

### 線程安全

- 所有 `registry.enqueue()` 操作受 `SessionRegistry._lock` 保護
- 多個 CPE 同時連線時互不影響
- 腳本執行在 HTTP 請求處理線程中

### 記憶體使用

- 腳本內容在執行時讀取，不常駐記憶體
- RPC 排隊到 `sess.pending`（deque）
- History 限制為 200 條（`HISTORY_LIMIT`）

### 性能考量

**單一腳本**：
- GET 模式：1 個 RPC（打包所有參數）
- SET 模式：N 個 RPC（每參數獨立）
- AUTO 模式：1 個 GET + N 個 SET

**建議**：
- 優先使用 GET 模式（效率高）
- SET 操作控制在 10 個參數內
- 避免在 PERIODIC 事件中執行大量 SET

### 與現有功能的整合

- ✅ 與 `auto_provision_cr` 共存（先執行 CR 佈建，再執行事件腳本）
- ✅ 與自動診斷共存（腳本 RPC 標記為 `diagnostic=True`）
- ✅ 與 Console 指令共存（腳本 RPC 與手動 RPC 同一隊列）
- ✅ 與 `open` 指令格式相容（腳本可用 `open` 測試）

### 擴展性

未來可能的擴展：
- 腳本中支援變數替換（如 `${SERIAL_NUMBER}`）
- 條件式腳本（根據參數值決定操作）
- 腳本鏈（一個腳本完成後觸發另一個）
- 遠端腳本（從 HTTP URL 載入）
- 腳本模板系統

---

## 附錄

### A. 完整配置範例

參見 `config_event_scripts_example.json`

### B. 腳本範例庫

參見 `prov/events/` 目錄

### C. 事件代碼參考

參見 TR-069 規範 Amendment 5 Section 3.7.1.5

### D. 故障排除檢查表

下載：`event_scripts_troubleshooting.pdf`（待建立）

---

**版本**：1.7  
**最後更新**：2026-09-21  
**作者**：ACS Development Team  
