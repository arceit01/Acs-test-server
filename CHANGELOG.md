# Changelog

All notable changes to the TR-069 ACS test tool are documented here.
Bump `VERSION` in `version.py` and add an entry below for each release.

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
