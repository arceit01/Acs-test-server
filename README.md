# TR-069 ACS 測試工具 v1.4

以 Python 標準函式庫實作的 TR-069/CWMP Auto Configuration Server（ACS）測試伺服器。
可讓 CPE（client）連線，並透過互動式 console 對 CPE 下發 Get / Set 參數等 RPC 指令。

## 功能

- 完整 CWMP session 流程：Inform → InformResponse → 空白 POST 輪詢 → 下發 RPC
- 可設定的 port 與 URL path（`config.json`）
- HTTP / HTTPS（TLS）可選
- 選擇性 HTTP Basic Auth（驗證連入的 CPE）
- 支援下發：`GetParameterValues`、`SetParameterValues`、`GetParameterNames`、`Reboot`、`FactoryReset`
- Connection Request：ACS 主動呼叫 CPE 的 URL 觸發 Inform（支援 Digest Auth）
- Bootstrap 自動佈建 Connection Request 帳密（產生 → 下發 → 寫回 config，
  見「Bootstrap 自動佈建 CR 帳密」）
- 解析並顯示 CPE 回應與 SOAP Fault、TransferComplete
- Set/Get 失敗自動診斷：收到 Fault 自動排入 get/names 查明路徑是否存在、
  writable 與型別（見「Set/Get 失敗自動診斷」）
- 互動式 console 操作，訊息即時顯示

## 環境需求

- Python 3.10+（僅使用標準函式庫，無需安裝套件）

## 快速開始

```bash
# 終端機 1：啟動 ACS server（首次執行若無 config.json 會自動產生預設值）
python3 acs_server.py -c config.json

# 終端機 2：啟動模擬 CPE 進行測試
python3 mock_cpe.py --url http://127.0.0.1:7547/acs --serial MOCK001 \
    --cr-port 18080 --cr-user admin --cr-pass secret
```

server 的 `connection_request` 設定需與 mock CPE 的 `--cr-user/--cr-pass` 一致，
才能對 mock CPE 執行 `cr` 指令。

### Console 操作範例

```
acs> list                                        # 列出已連線的 CPE
acs> select 1                                    # 選擇目標 CPE
acs[MOCK001]> get InternetGatewayDevice.DeviceInfo.ModelName
acs[MOCK001]> set InternetGatewayDevice.DeviceInfo.ModelName=NewModel-X
acs[MOCK001]> names InternetGatewayDevice.DeviceInfo.
acs[MOCK001]> reboot
acs[MOCK001]> cr                                 # 觸發 CPE 立即連線，送出排程中的指令
```

指令排入佇列後，會在該 CPE **下一次 session** 時依序送出：
CPE 主動 Inform 或由 `cr` 觸發皆可。回應與 Fault 會即時顯示在 console。

## Console 指令

| 指令 | 說明 |
|---|---|
| `list` | 列出所有已知 CPE |
| `select <編號\|序號>` | 選擇後續指令的目標 CPE |
| `info [目標]` | 顯示 CPE 詳細資訊（DeviceId、ConnectionRequestURL…） |
| `get <路徑> [路徑...]` | 排程 GetParameterValues |
| `set <路徑>=<值>[:型別] [...]` | 排程 SetParameterValues（見下方「參數型別處理」） |
| `names <路徑> [nextlevel]` | 排程 GetParameterNames |
| `find <關鍵字>` | 搜尋已學習的參數路徑（不分大小寫，顯示 writable 旗標） |
| `reboot [command_key]` | 排程 Reboot |
| `factoryreset`（`fr`） | 排程 FactoryReset |
| `fw download <url> [選項]` | 排程韌體升級 Download RPC（見「韌體升級測試」） |
| `cr [目標]` | 送出 Connection Request（HTTP GET + Digest Auth）給 CPE |
| `hist [目標]` | 顯示該 CPE 的訊息收發歷史 |
| `log` | 開/關原始 SOAP 封包記錄（預設關閉；摘要通知不受影響） |
| `status` | 伺服器狀態 |
| `sleep <秒>` | 暫停（供腳本化測試） |
| `quit` / `exit` / `q` | 結束 |

## 設定檔（config.json）

```jsonc
{
  "server": {
    "host": "0.0.0.0",          // 監聽位址
    "port": 7547,               // 監聽 port
    "path": "/acs",             // CWMP endpoint path
    "tls": {
      "enabled": false,         // true = 啟用 HTTPS
      "cert_file": "certs/server.crt",
      "key_file": "certs/server.key"
    },
    "auth": {                   // CPE 連入 ACS 的 Basic Auth
      "enabled": false,
      "username": "acsuser",
      "password": "acspass"
    }
  },
  "connection_request": {       // ACS 呼叫 CPE ConnectionRequestURL 的帳密
    "username": "",             // (Digest Auth)
    "password": "",
    "timeout": 10
  },
  "cwmp": {
    "parameter_key": "acs-test-key",  // SetParameterValues 附帶的 ParameterKey
    "log_soap": false,                // 顯示原始 SOAP 封包（預設關閉；
                                      // console 用 log 指令即時切換）
    "auto_provision_cr": true         // 0 BOOTSTRAP 時自動佈建 Connection
                                      // Request 帳密並寫回本檔
  },
  "logging": { "level": "INFO" }
}
```

設定檔缺漏的欄位會自動以預設值補齊；檔案不存在則自動產生。

## HTTPS 憑證

啟用 TLS 前，先產生 self-signed 憑證：

```bash
mkdir certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout certs/server.key -out certs/server.crt -subj "/CN=acs.local"
```

再將 `server.tls.enabled` 設為 `true`。真實 CPE 若驗證憑證失敗，
屬正常現象（self-signed），測試時可用 mock CPE（預設忽略憑證驗證）。

## Mock CPE（mock_cpe.py）

模擬一台 TR-069 設備，用於在沒有真實 CPE 時驗證 ACS：

```bash
python3 mock_cpe.py --url http://127.0.0.1:7547/acs --serial MOCK001 \
    [--oui AABBCC] [--product-class MockCPE] \
    [--cr-host 127.0.0.1] [--cr-port 18080] \
    [--cr-user admin --cr-pass secret]   # /cr 端點要求 Digest Auth
    [--bootstrap]                        # 第一次 Inform 用 0 BOOTSTRAP
    [--periodic 秒數]                    # 定期 Inform（2 PERIODIC）
    [--strict-set]                       # set 不存在的參數回 Fault 9003
                                         # （模擬 Arcadyan 等 firmware）
```

行為：

- 啟動後送 Inform（`1 BOOT`），之後以空白 POST 輪詢 ACS 直到 session 結束
- 內建參數表，正確回應 Get/SetParameterValues、GetParameterNames、Reboot 等
- 收到 Reboot 後 2 秒模擬重開機（再送一次 `1 BOOT` Inform）
- 監聽 `http://<cr-host>:<cr-port>/cr` 作為 Connection Request 端點
  （有設定帳密時要求 Digest Auth）

## 檔案結構

| 檔案 | 說明 |
|---|---|
| `acs_server.py` | 主程式：HTTP(S) server、CWMP session 處理 |
| `cwmp_messages.py` | SOAP/XML 訊息建構與解析 |
| `cpe_session.py` | Thread-safe CPE session 註冊表與 RPC 佇列 |
| `console_ui.py` | 互動式 console（cmd.Cmd） |
| `mock_cpe.py` | 模擬 CPE（測試用） |
| `config.json` | 設定檔 |

## 韌體升級測試（fw）

```
acs[MOCK001]> fw download http://192.168.1.10:8000/fw_v2.img
acs[MOCK001]> fw download http://srv/firmware_v3 --username admin --password secret \
                  --filesize 10485760 --cmdkey fw-upgrade-1
acs[MOCK001]> cr        # 觸發 session 送出 Download
```

- FileType 固定為 `1 Firmware Upgrade Image`；選項：`--username/--password`
  （CPE 抓檔帳密）、`--filesize`（預期大小）、`--targetfile`、`--delay`、
  `--cmdkey`（未指定自動產生）
- **檔名與副檔名不經驗證**：任何 URL 路徑皆可（`.img`、`.rbi`、無副檔名…）。
  TR-069 只傳遞 URL，CPE 只看檔案內容
- 標準非同步流程：CPE 回 `DownloadResponse Status=1`（下載中）→ 完成後開新
  session（event `7 TRANSFER COMPLETE`）送 TransferComplete 回報成功/失敗
  → 多數設備接著重開機進新韌體（event `1 BOOT`）
- console 會顯示 DownloadResponse 狀態與 TransferComplete 的 FaultCode（0=成功）

用 mock CPE + 本地 HTTP server 即可完整驗證：

```bash
mkdir /tmp/fw && dd if=/dev/urandom of=/tmp/fw/fw_v2.img bs=1M count=1
cd /tmp/fw && python3 -m http.server 8000 &
python3 mock_cpe.py --url http://127.0.0.1:7547/acs --serial MOCK001 ...
# console: select 1 -> fw download http://127.0.0.1:8000/fw_v2.img -> cr
```

## 參數路徑 Tab 自動補齊

在 `get` / `set` / `names` 後輸入部分路徑按 Tab 即可補齊（需 readline，
Linux/macOS 原生支援）：

- 補齊知識來自連線 CPE 的動態學習：Inform 參數、`get` 與 `names` 的回應。
  **執行過 `names <路徑>` 後，該層以下皆可補齊/列出**
- bash 風格操作：Tab 延伸共同前綴；再按 Tab 列出所有選項；
  唯一符合直接補滿。物件節點保留尾端 `.`，可逐層續補
  ```
  acs[MOCK001]> get Devic<Tab>          # → InternetGatewayDevice.
  acs[MOCK001]> get InternetGatewayDevice.DeviceInfo.<Tab><Tab>
  # 列出 ModelName / Manufacturer / ...
  ```
- 頂層（未輸入 `.` 前）支援子字串比對：`Devic` 可補成 `InternetGatewayDevice.`
- `set` 在輸入 `=` 之前補路徑；`select` / `info` / `hist` / `cr` 補齊序號
- `fw` 補齊子命令（`fw <Tab>` → `download`）與選項（`--<Tab>` 列出
  `--username/--password/--filesize/--targetfile/--delay/--cmdkey`）；
  URL 為任意輸入不補

## 參數型別處理（set）

SetParameterValues 收到 Fault 9003（Invalid arguments）通常是**型別不符**。
工具依下列優先順序決定送出的 xsi:type：

1. **明確指定**：值後加 `:型別`，如
   ```
   set Device.Services.VoiceService.1.VoiceProfile.1.Enable=true:boolean
   ```
   支援的型別別名：`bool`/`boolean`、`int`、`uint`、`string`/`str`、`double`/`float`、
   `dateTime`/`date`。boolean 值接受 `true/false/1/0/enabled/disabled/on/off`，
   自動正規化為 `1`/`0`。
2. **型別記憶**：若之前對該 CPE `get` 過同一參數，會記住 CPE 回報的 xsi:type
   並自動採用（建議流程：先 `get` 確認型別，再 `set`）。
3. **自動推斷**：`true/false` → boolean、整數 → int/unsignedInt、
   浮點 → double、其他 → string。

排程確認訊息會顯示實際將送出的 `[型別]`；型別衝突時顯示 WARNING。

收到 SetParameterValues 的 Fault 時，console 會顯示提示並**自動排入診斷**
（見下一節）。

## Set/Get 失敗自動診斷

Set 或 Get 收到 SOAP Fault（如 Arcadyan 對不存在/唯讀參數回 9003
"Invalid arguments"）時，ACS 會在同一 session 自動排入診斷 RPC：

- **set 失敗後**（每個失敗路徑去重、上限 5 筆）：
  1. `get <同一路徑>` — 回值 = 路徑存在（問題出在型別或唯讀）；
     再 Fault = 路徑在此 firmware 不存在
  2. `names <父物件> nextlevel` — 列出同層參數與 writable 旗標
     （writable=0 = 唯讀/被廠商鎖定）
- **get 失敗後**：`names <父物件> nextlevel` — 協助找出正確的實例編號

判讀流程：

```
<< FAULT FaultCode=9003 Invalid arguments.
auto-diagnosis queued:
  get Device.Services...SIP.OutboundProxy  (fault here = path does not exist)
  names Device.Services....SIP.  (writable=0 = read-only/locked)
```

- `get` 有回值且型別不同 → 用 `set <path>=<value>:<型別>` 重試
- `names` 顯示 `writable=0` → 參數被鎖定（如電信商 provisioning），TR-069 改不了
- 兩者都 Fault / 清單沒有該參數 → 路徑錯誤，用 `names` 往上逐層找正確編號

### 掃 vendor tree 找鎖定/解鎖參數

電信客製機種常以 vendor 節點管理寫入保護。先用 `names` 列舉，再以 `find`
過濾關鍵字（不分大小寫）：

```
names Device. true        # 頂層物件清單
cr                        # 觸發 session 送出
find X_TELUS              # 找 vendor 節點
find lock                 # 找疑似鎖定/解鎖參數（lock/unlock/admin/passwd/token）
```

## Bootstrap 自動佈建 CR 帳密

CPE 送出 event `0 BOOTSTRAP` 時，ACS 會自動（`cwmp.auto_provision_cr`，
預設開啟）模擬常見 provisioning script 的行為：

1. 產生憑證：
   - `Username = {OUI}-{ProductClass}-{SerialNumber}`
   - `Password = MD5(Username)`（32 位小寫 hex）
2. 依 Inform 參數前綴判斷資料模型後下發一筆 SetParameterValues：
   - 參數含 `Device.*` → `Device.ManagementServer.ConnectionRequestUsername/Password`
   - 否則 → `InternetGatewayDevice.ManagementServer.…`（TR-098 機種）
3. CPE 回覆 `Status=0` 後：帳密記錄到該 CPE session，並**寫回 config.json**
   的 `[connection_request]`；之後 `cr` 自動採用（優先序：該 CPE 佈建的帳密
   > config 全域帳密），`info` 會顯示 CR auth 狀態

注意：

- 每次 bootstrap 都會重新產生並重寫（值為確定性生成，冪等）
- 多台 CPE 各有專屬帳密時，config 只保留最後一台（單機測試情境；
  per-CPE 帳密在運行中仍各自生效）
- 佈建被拒（Fault）時不寫 config，CPE 維持舊帳密，console 顯示警告

## 已知限制

- 以 SerialNumber 識別 CPE；同一 TCP 連線綁定 session，多台 CPE 同時連線時
  以「最近活動」解析未帶 Inform 的請求（單機測試情境足夠）
- 不支援 Download/Upload RPC、物件多重例項寫入（add/delete object）
- XML 解析使用標準庫 ElementTree，未防護惡意 DTD 實體展開
  （僅建議在隔離的測試環境使用）
