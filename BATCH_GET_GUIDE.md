# 批次 GET 參數功能指南

## 簡介

ACS v1.6 新增 `open --get` 功能，允許從檔案批次查詢 CPE 參數值，所有參數會打包成單一 `GetParameterValues` RPC 請求，大幅提升效率。

## 快速開始

### 1. 建立參數清單檔案

建立一個文字檔案，每行一個參數路徑：

```bash
# prov/my_params.txt
Device.WiFi.Radio.1.Enable
Device.WiFi.Radio.1.Channel
Device.WiFi.SSID.1.SSID
Device.WiFi.SSID.1.Enable
```

### 2. 執行批次 GET

```bash
# 在 ACS console 中
acs> select 1                           # 選擇目標 CPE
acs[MOCK001]> open --get prov/my_params.txt   # 批次 GET
acs[MOCK001]> cr                        # 觸發 Connection Request
```

### 3. 查看結果

回應會自動顯示在 console：

```
>> GetParameterValuesResponse:
Device.WiFi.Radio.1.Enable = 1 [xsd:boolean]
Device.WiFi.Radio.1.Channel = 6 [xsd:unsignedInt]
Device.WiFi.SSID.1.SSID = MyNetwork [xsd:string]
Device.WiFi.SSID.1.Enable = 1 [xsd:boolean]
```

## 檔案格式

### 基本格式（純路徑）

最簡單的格式，每行一個參數路徑：

```
Device.WiFi.Radio.1.Enable
Device.WiFi.Radio.1.Channel
Device.WiFi.SSID.1.SSID
```

### 相容 SET 格式（path=value）

支援 SET 格式的檔案，GET 時會忽略 value 部分：

```
Device.WiFi.Radio.1.Enable=true:boolean
Device.WiFi.Radio.1.Channel=6:uint
Device.WiFi.SSID.1.SSID=MyNetwork
```

**優點**：同一檔案可用於兩種操作
- `open --get wifi.txt` → 查詢目前值
- `open wifi.txt` → 更新為指定值

### 註解與空行

支援 `#` 註解和空行，方便組織：

```
# WiFi Radio Configuration
Device.WiFi.Radio.1.Enable
Device.WiFi.Radio.1.Channel

# WiFi SSID Configuration
Device.WiFi.SSID.1.SSID
Device.WiFi.SSID.1.Enable
```

## 使用案例

### 案例 1：設定前先查詢

```bash
# 1. 查詢目前設定
acs[CPE001]> open --get prov/wifi_config.txt
acs[CPE001]> cr

# 2. 檢視回應後，修改檔案中的值

# 3. 批次更新設定
acs[CPE001]> open prov/wifi_config.txt
acs[CPE001]> cr
```

### 案例 2：故障排查

建立診斷參數清單：

```bash
# prov/troubleshoot.txt
Device.IP.Interface.1.Status
Device.IP.Interface.1.IPv4Address.1.IPAddress
Device.DHCPv4.Client.1.Status
Device.DNS.Client.Server.1.Enable
Device.Routing.Router.1.IPv4Forwarding.1.Status
```

快速診斷：

```bash
acs[CPE001]> open --get prov/troubleshoot.txt
acs[CPE001]> cr
```

### 案例 3：定期監控

建立監控參數清單並定期查詢：

```bash
# prov/monitoring.txt
Device.DeviceInfo.UpTime
Device.DeviceInfo.MemoryStatus.Total
Device.DeviceInfo.MemoryStatus.Free
Device.IP.Interface.1.Stats.BytesSent
Device.IP.Interface.1.Stats.BytesReceived
```

## 與其他指令的比較

### GET 指令（逐個查詢）

```bash
acs[CPE]> get Device.WiFi.Radio.1.Enable
acs[CPE]> get Device.WiFi.Radio.1.Channel
acs[CPE]> get Device.WiFi.SSID.1.SSID
# 產生 3 個獨立的 GetParameterValues RPC
```

### open --get（批次查詢）

```bash
acs[CPE]> open --get wifi_params.txt
# 產生 1 個包含所有參數的 GetParameterValues RPC
```

**優勢**：
- 效率更高（單一請求）
- 響應更快（減少網路往返）
- 易於管理（參數清單檔案化）
- 可重複使用（標準化查詢）

## SET vs GET 模式對比

| 特性 | SET 模式（預設） | GET 模式（--get） |
|------|----------------|-----------------|
| 指令 | `open <file>` | `open --get <file>` |
| 檔案格式要求 | `path=value[:type]` | `path`（或 `path=value`，忽略 value） |
| RPC 數量 | N 個（每參數一個） | 1 個（包含所有參數） |
| RPC 類型 | SetParameterValues | GetParameterValues |
| 用途 | 批次設定更新 | 批次參數查詢 |

## 範例檔案

專案提供以下範例檔案：

### prov/get_voice.txt
VoIP 配置參數查詢範例（純路徑格式）

### prov/get_device_info.txt
設備資訊與管理伺服器參數（混合格式，展示相容性）

### prov/voice.txt
原有 SET 範例（也可用於 GET）

## 錯誤處理

如果檔案格式有誤，整批操作會被取消：

```
Line 5: empty parameter name in '=value'
```

修正錯誤後重新執行即可。

## 技術細節

- 所有參數路徑會收集並打包成單一 `GetParameterValues` RPC
- RPC 排隊機制與其他指令相同
- 回應解析自動處理型別資訊（xsi:type）
- 支援任意數量的參數（實務上受 CPE 限制）

## 最佳實踐

1. **組織參數檔案**：按功能分類（wifi.txt, voip.txt, wan.txt）
2. **使用註解**：清楚標記各參數用途
3. **版本控制**：將參數檔案納入 Git 管理
4. **標準化命名**：建立團隊共用的參數清單
5. **先 GET 後 SET**：修改前先查詢目前值

## 故障排除

### 問題：檔案找不到

```
Cannot open 'params.txt': [Errno 2] No such file or directory
```

**解決**：使用相對路徑（如 `prov/params.txt`）或絕對路徑

### 問題：參數路徑錯誤

CPE 回應 Fault 9003（Invalid arguments）

**解決**：
1. 使用 `names` 指令確認正確路徑
2. 檢查實例編號（如 `.1.`、`.2.`）
3. 參考 CPE 資料模型文件

### 問題：CPE 不回應

**解決**：
1. 檢查 `ConnectionRequestURL` 是否正確（`info` 指令）
2. 確認網路連通性
3. 查看 CPE 是否支援該參數

## 更多資訊

- 完整文件：`README.md`
- 變更記錄：`CHANGELOG.md`
- 線上說明：在 console 輸入 `help open`
