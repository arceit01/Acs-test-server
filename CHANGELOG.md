# Changelog

All notable changes to the TR-069 ACS test tool are documented here.
Bump `VERSION` in `version.py` and add an entry below for each release.

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
