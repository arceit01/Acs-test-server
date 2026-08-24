# Changelog

All notable changes to the TR-069 ACS test tool are documented here.
Bump `VERSION` in `version.py` and add an entry below for each release.

## [1.4] - 2026-08-24

### Added
- Bootstrap 自動佈建 Connection Request 帳密（`cwmp.auto_provision_cr`，
  預設開啟）：CPE 送 `0 BOOTSTRAP` 時產生 Username =
  `{OUI}-{ProductClass}-{SerialNumber}`、Password = 小寫 MD5 hex，依資料
  模型（Device.* / InternetGatewayDevice.*）下發 SetParameterValues；
  CPE 確認後帳密記錄至該 CPE session 並寫回 config.json `[connection_request]`。
  `cr` 帳密解析順序改為：該 CPE 佈建帳密 > config 全域；佈建失敗不動 config
- `info` 新增 CR auth 狀態列；`cr` 成功訊息標示認證來源（provisioned/config）
- mock_cpe.py `/cr` 端點優先採用 TR-069 寫入的 ConnectionRequestUsername/
  Password 驗證 Digest（無則退回 --cr-user/--cr-pass），可完整驗證佈建閉環
- Set/Get 失敗自動診斷：SetParameterValues 或 GetParameterValues 收到 SOAP
  Fault 時，自動排入後續 RPC 並在同一 session 內顯示結果
  - Set 後：對每個失敗路徑（去重、上限 5 筆）送 `GetParameterValues(同路徑)`
    （回值 = 路徑存在、問題在型別/唯讀；再 Fault = 路徑不存在）+
    `GetParameterNames(父物件, nextlevel)`（writable=0 = 唯讀/鎖定）
  - Get 後：對父物件送 `GetParameterNames(nextlevel)`，協助找出正確實例編號
- `find <關鍵字>` 指令：以不分大小寫子字串搜尋已學習的參數路徑
  （來源 Inform/get/names 回應），顯示已知 writable 旗標；
  供掃 vendor tree 找鎖定/解鎖參數（X_* 節點、lock/passwd/token 等）
- GetParameterNamesResponse 的 writable 旗標現會記錄（`param_writable`）
- mock_cpe.py 新增 `--strict-set`：set 不存在的參數時回 Fault 9003
  "Invalid arguments."（模擬 Arcadyan 等 firmware 行為，供測試驗證）

### Changed
- Set Fault 提示文字擴充：涵蓋型別不符、唯讀（廠商鎖定）、路徑不存在三種原因

## [1.3] - 2026-08-21

### Changed
- 原始 SOAP 封包顯示改為**預設關閉**（`cwmp.log_soap` 預設 false）：
  console 只顯示簡潔摘要（參數值等照常）；需要看封包時用 `log` 指令
  即時切換或改 config。既有 config.json 已寫入 `log_soap: true` 者不受影響

### Added
- `fw` 指令 Tab 補齊：子命令（`fw <Tab>` → `download`）與選項
  （`--<Tab>`）；選項清單抽成 `FW_OPTIONS` 常數與 `do_fw` 共用

### Docs
- 釐清韌體檔名/副檔名不經驗證（`.img`、無副檔名皆可），範例改為混合型態

## [1.2] - 2026-08-21

### Added
- 韌體升級功能：`fw download <url> [選項]` 排程 TR-069 Download RPC
  （FileType "1 Firmware Upgrade Image"，支援 --username/--password/
  --filesize/--targetfile/--delay/--cmdkey）
- DownloadResponse 專屬顯示（Status 0=已完成 / 1=進行中、StartTime/CompleteTime）
- mock CPE 支援完整非同步下載流程：背景實際下載 → 新 session（event
  "7 TRANSFER COMPLETE"）送 TransferComplete → 模擬升級後重開機（1 BOOT）

## [1.1] - 2026-08-21

### Added
- Parameter 路徑 Tab 自動補齊（bash 風格：Tab 延伸共同前綴、再按 Tab 列出選項）
  - 補齊來源為動態學習：Inform ParameterList、GetParameterValuesResponse、
    GetParameterNamesResponse（執行過 `names <路徑>` 後能力自動增強）
  - `get` / `names` 補齊路徑；`set` 於輸入 `=` 前補路徑；
    `select` / `info` / `hist` / `cr` 補齊序號
  - 頂層支援子字串比對（`Devic` → `InternetGatewayDevice.`）
  - 物件節點保留尾端 `.`，可逐層續補

## [1.0] - 2026-08-21

### Added
- 首次發布：TR-069/CWMP ACS 測試伺服器（Python 3.10+，僅標準函式庫）
- 可設定的 port / URL path / TLS（HTTPS）/ Basic Auth（`config.json`）
- CWMP session 流程：Inform → InformResponse → 空白 POST 輪詢 → 下發 RPC
- 支援下發 GetParameterValues、SetParameterValues、GetParameterNames、
  Reboot、FactoryReset；解析回應、SOAP Fault 與 TransferComplete
- Connection Request（ACS → CPE，支援 Digest Auth）
- 互動式 console：list/select/info/get/set/names/reboot/factoryreset/cr/
  hist/log/status/sleep/quit
- 詳細 help：`help <command>` 與 `<command> ?` 顯示 Usage/Arguments/
  Examples/Notes
- 參數型別處理：明確型別語法 `set path=value:type`、CPE 回報型別記憶、
  自動推斷與 boolean 正規化（enabled/disabled/on/off → 1/0）
- Fault 解析大小寫容錯（相容 `<cwmp:Fault>` 等非標準大小寫）
- SetParameterValues Fault 提示（引導用 get 查型別後重試）
- mock_cpe.py 模擬 CPE（含 Connection Request 端點與 Reboot 重連模擬）
