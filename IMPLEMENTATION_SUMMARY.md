# 實作摘要：批次 GET 參數功能

## 專案資訊

- **版本**: 1.5 → 1.6
- **實作日期**: 2026-09-21
- **功能名稱**: 批次 GetParameterValues (open --get)

## 需求回顧

使用者希望能夠：
1. 從檔案讀取多個參數名稱
2. 一次性發送 GetParameterValues 請求到 CPE
3. 取得 CPE 所有指定參數的值

## 解決方案

擴充現有 `open` 指令，新增 `--get` 選項：
- 維持原有 SET 模式行為不變
- 新增 GET 模式，支援批次參數查詢
- 檔案格式向下相容，同一檔案可用於 GET/SET 兩種操作

## 檔案變更

### 1. console_ui.py

#### 修改：do_open() 方法 (行 814-862)

**變更前**:
- 僅支援 SET 操作
- 檔案格式必須為 `path=value[:type]`
- 每個參數產生獨立的 SetParameterValues RPC

**變更後**:
- 支援 `--get` 選項切換為 GET 模式
- GET 模式：
  - 檔案格式支援純路徑或 `path=value`（忽略 value）
  - 所有參數打包成單一 GetParameterValues RPC
- SET 模式：維持原有行為

**關鍵實作**:
```python
# 參數解析
tokens = shlex.split(arg)
get_mode = False
filepath = None
for token in tokens:
    if token == "--get":
        get_mode = True
    elif not filepath:
        filepath = token

if get_mode:
    # GET 模式：提取參數路徑
    param_names = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, sep, raw = line.partition('=')
        name = name.strip()
        param_names.append(name)
    
    # 排隊單一 GetParameterValues RPC
    args = {"names": param_names}
    summary = f"{len(param_names)} parameter(s)"
    rpc = OutboundRPC("GetParameterValues", args, summary)
    self.registry.enqueue(sess.serial, rpc)
else:
    # SET 模式：原有邏輯不變
    ...
```

#### 修改：HELP 字典 (行 222-231)

更新 `open` 指令的幫助說明：
- 新增 `--get` 選項說明
- 新增使用範例
- 說明兩種模式的差異

### 2. README.md

#### 新增章節："批次參數操作（open）"

詳細說明：
- SET 模式操作方式與檔案格式
- GET 模式操作方式與檔案格式
- 檔案格式通用規則
- 使用流程範例

#### 修改：Console 指令表

更新 `open` 指令說明為 `open [--get] <檔案>`

### 3. CHANGELOG.md

新增 v1.6 版本記錄：
- 詳細記錄 `open --get` 功能
- 說明檔案格式相容性
- 列出新增的範例檔案

### 4. version.py

版本號更新：`1.5` → `1.6`

### 5. 新增檔案

#### prov/get_voice.txt
- VoIP 配置參數查詢範例
- 純路徑格式
- 包含詳細註解

#### prov/get_device_info.txt
- 設備資訊與管理伺服器參數
- 混合格式（展示相容性）
- 包含純路徑和 `path=value` 格式

#### test_open_get.py
- 單元測試腳本
- 測試檔案解析邏輯
- 測試參數解析
- 測試 RPC 創建

#### demo_open_get.sh
- 功能演示腳本
- 展示使用範例
- 執行單元測試

#### BATCH_GET_GUIDE.md
- 完整使用指南
- 快速開始教程
- 使用案例與最佳實踐
- 故障排除

#### IMPLEMENTATION_SUMMARY.md
- 本檔案
- 實作總結與變更記錄

## 技術細節

### 參數解析流程

```
讀取檔案
  ↓
過濾註解和空行
  ↓
提取參數路徑（partition('=')）
  ↓
收集所有路徑到列表
  ↓
建立 GetParameterValues RPC
  ↓
排入佇列等待發送
```

### RPC 結構

```python
OutboundRPC(
    method="GetParameterValues",
    args={"names": ["path1", "path2", ...]},
    summary="N parameter(s)"
)
```

### 與現有架構的整合

- 使用現有的 `OutboundRPC` 類別
- 整合到現有的 RPC 佇列機制
- 複用現有的 session 管理
- 回應處理使用現有的解析器

## 測試驗證

### 單元測試
- ✓ 檔案解析邏輯（4 個參數）
- ✓ 參數解析（--get 標誌）
- ✓ RPC 創建（GetParameterValues）

### 語法檢查
- ✓ 所有 Python 檔案編譯成功
- ✓ 無語法錯誤

### 功能測試
- ✓ SET 模式（原有功能不受影響）
- ✓ GET 模式（新功能）
- ✓ 檔案格式相容性

## 使用範例

### 基本使用

```bash
# 1. 啟動 ACS server
python3 acs_server.py -c config.json

# 2. CPE 連線後，在 console 操作
acs> select 1
acs[MOCK001]> open --get prov/get_voice.txt
Queued GetParameterValues for MOCK001: 7 parameter(s) from 'prov/get_voice.txt'

acs[MOCK001]> cr
# 回應自動顯示
```

### 進階使用

```bash
# 先查詢目前值
acs[CPE]> open --get prov/wifi.txt
acs[CPE]> cr

# 檢視回應後修改檔案，然後批次更新
acs[CPE]> open prov/wifi.txt
acs[CPE]> cr
```

## 效能優勢

### 傳統方式（逐個 GET）
```
get param1 → RPC1 → Response1
get param2 → RPC2 → Response2
...
get paramN → RPCN → ResponseN

總請求數：N
網路往返：N 次
```

### 批次 GET（open --get）
```
open --get file → RPC(param1...paramN) → Response(all)

總請求數：1
網路往返：1 次
```

**效能提升**：
- N 個參數節省 N-1 次網路往返
- 減少 CWMP session 開銷
- 提高大量參數查詢效率

## 向後相容性

- ✓ 原有 `open` 指令行為不變
- ✓ 現有參數檔案無需修改
- ✓ 新舊檔案格式完全相容
- ✓ 所有現有功能正常運作

## 未來擴展可能

1. **批次混合操作**：同一檔案混合 GET/SET 指令
2. **條件式參數**：根據 GET 結果決定 SET 內容
3. **參數範本**：支援萬用字元或正規表示式
4. **JSON 格式**：支援 JSON 參數檔案格式
5. **匯出功能**：將 GET 結果匯出為檔案

## 結論

本次實作成功完成了批次 GET 參數功能，主要成就：

✅ 擴充 `open` 指令，新增 `--get` 選項  
✅ 支援檔案格式向下相容  
✅ 單一 RPC 請求提升效率  
✅ 提供完整文件與範例  
✅ 通過所有測試驗證  
✅ 維持向後相容性  

功能已可立即投入使用，滿足使用者需求。
