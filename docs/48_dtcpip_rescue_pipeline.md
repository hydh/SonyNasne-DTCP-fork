# 48. DTCP-IP 経由の既存録画救出パイプライン (pydtcpip をエンジンとする実装と、資格情報未配置状態での検証)

## 1. 位置づけと範囲

- 既存録画の救出経路として、本人が 2026-11-17 に **DTCP-IP 経由** を選定した。復号オラクル経路 (docs/03) と資格情報の直接抽出は、鍵素材に触れるため採らない。本書は、その経路のパイプラインを構築し、資格情報が未配置の状態で検証した記録である。
- 合意済みの分担 (線引き):
  - **鍵は本人が `credentials.env` にだけ配置し、書き込む。** それ以外の場所 (チャット、他のファイル、コマンドライン) には出さない。
  - パイプライン側のプログラムは、鍵の値を **読まない・出さない・検証しない**。
  - エンジン (AKE と復号) は **pydtcpip** (docs/32) が担い、資格情報は pydtcpip 自身が env ファイルから読み込む。
- 実機側の前提 (プロファイル `sie_nasne` の自動一致、DIDL の形、`av:COGCount` の所在、メディア HEAD の標準形) は docs/37 で照合済み。
- **本書の範囲はパイプラインの構築と未配置状態での検証まで。AKE の実走は行っていない (行えない)。** AKE 完走と TS 正常性の確認は、本人が資格情報を配置した後の初回 fetch で行う (§5)。

## 2. 設計 (事実)

### 2.1 構成

作業領域 (開発側): `SonyNasne-DTCP.work/2026-11-17-dtcpip-rescue/`

```
bin/list_recordings.py   列挙 (資格情報なし)
bin/rescue.py            ドライバ (list / fetch / fetch-all)
data/credentials.env     資格情報 (本人のみが書く。権限 600、data/ は 700)
data/srm.bin             (初回 AKE 成功時に pydtcpip が自動保存する SRM)
out/listings/            列挙結果 JSON (実行毎)
out/<content_id>-<タイトル>.ts        救出した復号済み TS
out/<content_id>-<タイトル>.ts.json   メタデータ + 取得記録 (SHA-256 つき)
out/manifest.json / out/SHA256SUMS.txt 救出済み一覧
out/.*.partial           転送途中のファイル (失敗時に残る。manifest には入らない)
logs/                    実行ログ (pydtcpip の stderr を含む)
```

### 2.2 列挙

- pydtcpip の DLNA スタック (SSDP 発見 + ContentDirectory Browse の再帰) で録画一覧を取得し、JSON で出す。資格情報は不要。
- ライブチューナーのチャンネルは DIDL 上 `object.item.videoItem.videoBroadcast` として現れるため除外する (pydtcpip CLI 自身の録画/チャンネルの区別と同じ)。
- 同一録画は all / ジャンル別 / 日付別の各コンテナに別々の object ID で現れる。録画の同一性は object ID 末尾の `pvr?id=` の値 (content_id) とし、代表エントリは `0/video/all/` のものを採る。
- JSON の項目: タイトル、content_id と object ID、日時、長さ、チャンネル名、概要、ジャンル、res 一覧 (URL、protocolInfo、cleartextSize)、残コピー数 (`av:COGCount` 由来)、Move 可否。

### 2.3 転送ドライバと資格情報の流れ

- ドライバは pydtcpip CLI を子プロセスとして起動する:
  `pydtcpip --data-dir <data/> stream --server <description URL> --id <object ID> --credentials <data/credentials.env>`
  標準出力 (復号済み TS) をファイルへ、標準エラー (ログ・進捗) を `logs/` へ受ける。
- ドライバは資格情報ファイルを **開かない**。参照はパスによってのみ行い、存在確認もパスの有無まで。
- pydtcpip の仕様では環境変数 (`PYDTCPIP_CERTIFICATE` / `PYDTCPIP_PRIVATE_KEY`) が env ファイルより優先される (pydtcpip `store.py` の `_CredentialSettings`)。ドライバは子プロセスの環境から `PYDTCPIP_*` を除去し、**資格情報の出所を `data/credentials.env` だけに限定する**。
- env ファイルの変数名と形式は pydtcpip 自身の公開インタフェースである: `PYDTCPIP_CERTIFICATE` と `PYDTCPIP_PRIVATE_KEY`、値は hex 文字列。テンプレート (変数名のみ、値は空、権限 600) を `data/credentials.env` に配置済み。
- 転送方式は pydtcpip の **`stream`** を使う。再生と同種の受信であり、**コピーを消費せず、nasne 側の状態も変更しない**。pydtcpip の `move` / `receive` (ダビング) はコピーを消費するため、このパイプラインでは使わない (ドライバは呼び出さない)。res の選択は pydtcpip CLI の既定 (original resource = 保存形式) に従う。
- SRM は pydtcpip の仕組みで `data/srm.bin` に保存・更新される (初回 AKE 成功時以降)。パイプライン側は触れない。
- 失敗時の意味論: リトライなしの単一試行。終了コード非 0 または 0 バイトなら失敗として、途中データは `.partial` に残し manifest には入れない。成功時はアトミックにリネームし、SHA-256 を計算して sidecar JSON と manifest を更新する。既救出のタイトルは自動スキップ (`--force` で再取得)。

### 2.4 ログの範囲

- `logs/` に残るのは、録画 ID・タイトル・資格情報ファイルのパス・存在の有無・pydtcpip の終了コード・バイト数と、pydtcpip 自身の stderr 出力のみ。鍵の値は構造上含まれない (読み込み失敗時の pydtcpip のエラーメッセージは、ファイルパスと変数名のみを含む形であることを §4 で実物確認した)。

## 3. 使い方

作業ディレクトリは `2026-11-17-dtcpip-rescue/`。手順の正本は同フォルダの `README.md`。

```
# 列挙 (資格情報なし)
python3 bin/rescue.py list

# 資格情報の配置 (本人の作業): data/credentials.env の2変数に値を書く

# 単一タイトルの試行 (content_id でも object ID でも指定可)
python3 bin/rescue.py fetch --id <content_id>

# 全件
python3 bin/rescue.py fetch-all

# 検証
cd out && sha256sum -c SHA256SUMS.txt
```

資格情報の絶対パスは次の 1 箇所だけである:
`/home/markun/GitTmp/myClaude/SonyNasne-DTCP.work/2026-11-17-dtcpip-rescue/data/credentials.env`

## 4. 検証 (2026-11-17、資格情報未配置の状態で実施。事実)

### 4.1 列挙 (実機)

- SSDP 発見で実機 1 台が検出され、プロファイル `sie_nasne` が自動一致した (description の location は `http://192.168.11.129:58888/`)。
- ユニークな録画は **5 件**。全件に `av:COGCount` が付き (値 9〜10)、original res の cleartextSize 合計は **10,334,390,016 バイト (約 10.3 GB)**。出力先ファイルシステムの空きは約 1.3 TB で、容量は十分である。
- 列挙結果 JSON は作業領域の `out/listings/` に保存した (録画タイトル等を含むため、docs/37 の先例に倣い本書には転記しない)。

### 4.2 空テンプレートでの fetch (失敗の確認)

- 録画 1 件を指定して fetch を実行したところ、pydtcpip は **資格情報の読み込み段階で即座に終了コード 1 で停止** した (開始と終了が同一秒)。書き込みは 0 バイト、`.partial` は空のまま残った。
- ログに残ったエラーメッセージは「指定パスに資格情報を置くか、環境変数 `PYDTCPIP_CERTIFICATE` と `PYDTCPIP_PRIVATE_KEY` を設定せよ」という趣旨で、**パスと変数名のみ** を含み、値は一切含まれない。
- pydtcpip CLI の `stream` 実装では資格情報の読み込みが全てのネットワーク処理に先行するため、この失敗は nasne への接続 (AKE ポートを含む) を一切行わない段階で起きる。中途半端な接続やリトライ暴走はない。

### 4.3 ファイル未配置での fetch (失敗の確認)

- テンプレートを一時的に退避して (ファイルが存在しない状態で) 同じ fetch を実行したところ、「Credentials file not found: <パス>」で終了コード 1、0 バイトで停止した。同経路のきれいな失敗である。
- テンプレートは SHA-256 一致を確認して復元し、権限 600 を再設定した。SRM ファイルは生成されていない (AKE 未実施の証跡)。nasne 側の状態変更も行っていない (実施したのは Browse と本節の失敗確認のみ)。

## 5. 残件

- **AKE 実走と TS 正常性の確認** (本人が `data/credentials.env` に資格情報を配置した後の初回 fetch で実施する)。確認観点: AKE 完走、受信 TS の同期と内容の正常性、SRM の保存、以後の fetch での SRM 利用。
- 長時間転送 (数 GB 級) の所要時間と、中断時の `.partial` の扱い (現設計では再開機能なし。pydtcpip の `stream` には再開がないため、失敗したタイトルは頭から取り直す)。
- 本パイプラインの対象は「nasne が現在一覧に出している録画」だけである。削除済み録画のカービング (docs/23) の線とは別であり、相互に影響しない。
- torne mobile HB 側の内蔵 DTCP-IP 実装 (再生用) とは別線であり、本パイプラインは PC 側の救出専用である。
