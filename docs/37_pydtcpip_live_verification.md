# 37. pydtcpip 実機検証 (1): discover / dump による sie_nasne 前提の照合

## 1. 位置づけと範囲

- docs/32 の静的調査で残った未確定点のうち、実機検証の第一歩として設計されていた「資格情報なし・コピー消費なしの `dump` による応答採取」を実施した記録。
- 実施範囲はここまで。AKE (相互認証) 以降は資格情報 (DTLA 署名の証明書 + 機器秘密鍵の正規ペア) が必要な領域であり、本書では実施していない。
- 本書で「事実」とするのは実機応答から直接確認できたものだけとし、評価は「評価」と明記する。

## 2. 方法 (事実)

- 対象: 公式ファームウェア稼働中の nasne 実機 (同一 LAN 内)。
- 実行環境: LAN 内の Linux 機。pydtcpip v0.1.0 (コミット `e726fc548c01701f5949f8a93d47b45b038395df`) を uv で構築した venv (Python 3.13) で実行した (ホストのシステム Python は 3.12 で、pyproject の要求 `>=3.13` を満たさないため)。
- 手順: `pydtcpip discover` で発見 → `pydtcpip dump <出力先>` (max-recordings は既定の 5)。

## 3. 結果 (事実)

### 3.1 discover

- 実機が 1 台検出され、デバイスプロファイル **`sie_nasne` が自動選択された** (modelName による照合が実機で成立)。

### 3.2 description / SCPD

- description の主要項目: friendlyName = `nasne`、manufacturer = `Sony Computer Entertainment Inc.`、modelDescription = `nasne`、modelName = `nasne`。
- SCPD を取得できたサービス: ContentDirectory、ConnectionManager、X_ScheduledRecording、X_PvrControl。

### 3.3 Browse / 録画メタデータ / メディア HEAD

- Browse 応答 19 件、録画メタデータ (DIDL) とメディア HEAD 応答を 4 件採取した。
- メディア HEAD は **200** で、Content-Type は `application/x-dtcp1` に `DTCP1HOST` / `DTCP1PORT` / `CONTENTFORMAT="video/vnd.dlna.mpeg-tts"` パラメータを伴う、docs/32 §2.2 が AKE の入口として記述した標準形そのものだった。
- HEAD のその他の主要項目: Server = `Linux/2.6 UPnP/1.0 nasne/1.0`、contentFeatures.dlna.org に `DLNA.ORG_PN=DTCP_AVC_TS_JP_AAC_T` (採取した 3 倍録画タイトル)、`DTCP.COM_FLAGS=C0000000`、transferMode.dlna.org = `Streaming`。
- DIDL 側の res の protocolInfo は HEAD と整合し、第 2 の res には `SONY.COM_PN=DTCP_AVC_TS_SD_30_JP_AAC_T` があった。
- **`av:COGCount` 要素が DIDL に存在した** (採取したタイトルでは 10)。sie_nasne プロファイルが残コピー数として参照する前提と一致。
- Browse / HEAD のいずれでも **403 は返らなかった**。未登録のクライアントに対しても、メタデータとメディア HEAD は提供される。

## 4. 評価

- sie_nasne プロファイルの前提 — modelName の一致、DIDL の形、protocolInfo の形式、`av:COGCount` の所在 — は **実機で全て成立した**。
- docs/32 の未確定点のうち「dump による無消費の採取」は本書で完了。残る分岐は AKE 以降 (証明書ペアの調達と nasne 側の受け入れ) で、本書の範囲外。

## 5. 成果物の所在

- 採取データ一式は開発側の作業領域 (`2026-11-15-pydtcpip/dump1/`) に保存した。無マスクのため公開しない (共有が必要な場合は `dump --mask-private` で取り直す)。
