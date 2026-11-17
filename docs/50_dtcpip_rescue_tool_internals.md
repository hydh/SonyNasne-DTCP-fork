# 50. dtcpip-rescue ツールの内部仕組み

## 1. 位置づけと範囲

- 本書は、正式ツール [tools/dtcpip-rescue/](../tools/dtcpip-rescue/) の **内部仕組みの正本** である。ツール README は本人の指示で「使い方」だけの軽い文書に保つ方針となり、仕組みの詳細は本書へ切り出した (2026-11-17)。
- 構築の経緯と未配置状態での検証は [docs/48](48_dtcpip_rescue_pipeline.md)、正式化・AKE 実走・Windows 実機検証・GUI・転送時間計測・手動登録の検証記録は [docs/49](49_dtcpip_rescue_tool_and_windows.md)。本書は検証記録を重複させず、現行実装の構造だけを記す。
- 本書でも鍵の値・個体を特定できる値は書かない (作法は [AGENTS.md](../AGENTS.md) §2.3)。

## 2. 鍵の分担の仕組み

### 2.1 原則

- **鍵は利用者本人が `credentials.env` にだけ配置し、書き込む。** それ以外の場所 (チャット、他のファイル、コマンドライン) には出さない。
- ツール側のプログラム (CLI / GUI とも) は、鍵の値を **読まない・出さない・検証しない**。エンジン (AKE と復号) は pydtcpip が担い、資格情報は pydtcpip 自身が env ファイルから読み込む。
- ツールに鍵は同梱されない。リポジトリに入っているのは空テンプレート (`credentials.env.example`) だけである。

### 2.2 資格情報の出所をファイルだけに限定する仕組み

- pydtcpip の仕様では、環境変数 (`PYDTCPIP_CERTIFICATE` / `PYDTCPIP_PRIVATE_KEY`) が env ファイルより **優先される** (pydtcpip `store.py` の `_CredentialSettings`、docs/48 §2.3)。
- そのためドライバ (`rescue.py` の `child_env()`) は、pydtcpip を子プロセスとして起動する際、その環境から **`PYDTCPIP_` で始まる変数を全て除去する**。これにより、呼び出し側シェルの環境に同名変数があっても紛れ込まず、資格情報の出所は `credentials.env` だけになる。
- ドライバ自身も資格情報ファイルを **開かない**。参照はパスによってのみ行い、存在確認もパスの有無までである。
- env ファイルの変数名と形式は pydtcpip 自身の公開インタフェースである: `PYDTCPIP_CERTIFICATE` と `PYDTCPIP_PRIVATE_KEY`、値は hex 文字列。

### 2.3 GUI の配置状態判定

- GUI の「配置状態」は、資格情報ファイルを **開かず**、ファイルの有無とサイズ (同梱の空テンプレートとの比較) だけから判定する。表示は4種: 「未配置 (ファイルがありません)」「未配置 (空ファイルです)」「未配置 (空テンプレートのまま)」「配置済み (ファイルサイズからの推定)」。
- 判定規則: ファイルが無い・0 バイト・テンプレートと **完全同サイズ** のいずれかなら未配置、それ以外 (テンプレートとサイズが異なる) なら配置済み。根拠は、記入済みファイルには hex 値 2 本 (合計 216 文字) が必ず入るため、テンプレートと同サイズにはなり得ないこと。テンプレートに記入した形はテンプレートより大きく、2 行だけの最小構成で手書きした形はテンプレート (コメント主体で 770 B) より小さくなる。
- **不具合と修正 (2026-11-17、Mac 実機で判明)**: 従来の判定は「サイズがテンプレート以下なら未配置」で、上記の最小構成の手書きファイル (約 260 B) を値入りでも未配置と誤判定した。fetch は同じファイルで成功するため、「fetch はできるのに配置状態は未配置」という不整合になった。真因はパス解決の食い違いではなく、サイズ比較の前提 (配置ファイルはテンプレートのコピーに記入した形で、テンプレートより大きいという思い込み) にあった。同日に上記の「同サイズのみ未配置」へ改めた。
- 判定に使うパスの解決は一元化した: 状態表示・接続確認・一覧・fetch はすべて、入力欄から解決した同一の Config を使う (`_display_config()`)。また配置状態は各アクションの開始時に再評価するため、起動後に同じパスへファイルを置いた・差し替えた場合も、再起動なしで表示に反映される。パスの解決はスクリプト位置基準で CWD に依存しないため、`.command` ランチャーのような CWD 不定の起動でも、表示・判定と実際に使われるファイルは一致する。
- パスの表示・変更・フォルダ開きも、ファイル内容には一切触れない。

### 2.4 ログの範囲

- `logs/` に残るのは、録画 ID・タイトル・資格情報ファイルのパス・存在の有無・pydtcpip の終了コード・バイト数と、pydtcpip 自身の stderr 出力のみである。鍵の値は構造上含まれない (読み込み失敗時の pydtcpip のエラーメッセージがファイルパスと変数名のみを含むことは docs/48 §4 で実物確認済み)。

## 3. 転送方式の内部

### 3.1 子プロセスの起動形

ドライバは pydtcpip CLI を子プロセスとして起動する:

```
pydtcpip --data-dir <data-dir> stream --server <description URL> --id <object ID> --credentials <credentials.env のパス>
```

- 標準出力 (復号済み TS) を出力ファイルへ、標準エラー (ログ・進捗) を `logs/` へ受ける。
- 子プロセスの環境は §2.2 の除去に加え、§5.3 の UTF-8 強制を施したものを使う。

### 3.2 `stream` を使う理由、`move` / `receive` を使わない理由

- 転送方式は pydtcpip の **`stream`** である。これは再生と同種の受信であり、**コピーを消費せず、nasne 側の状態も変更しない**。
- pydtcpip の `move` / `receive` (ダビング) は **コピーを消費する** ため、このツールでは使わない (ドライバは呼び出さない)。
- res の選択は pydtcpip CLI の既定 (original resource = 保存形式) に従う。3倍録画の res 構成 (原本が `quality=x3` の AVC TS であること等) の実測は docs/49 §2。

### 3.3 SRM (`srm.bin`) の扱い

- SRM は pydtcpip の仕組みで `--data-dir` に保存・更新される (初回 AKE 成功時以降)。ツール側は読み書きしない。
- data-dir の既定値を「資格情報ファイルのあるディレクトリ」としているのは、SRM が資格情報の隣に保存される配置を保つためである (経緯は docs/49 §3)。

### 3.4 失敗時の意味論と保存

- リトライなしの単一試行。終了コード非 0 または 0 バイトなら失敗として、途中データは `.partial` に残し、manifest には入れない。
- 成功時はアトミックにリネームし、SHA-256 を計算して sidecar JSON (`<content_id>-<タイトル>.ts.json`) と manifest を更新する。
- 既に manifest にある録画は自動スキップする (`--force` で再取得)。
- ファイル名のタイトル部分は `sanitize_title()` で整形する (pydtcpip CLI と同じ規則: ファイル名に使えない文字を `_` に置換し、UTF-8 で 200 バイトまでに切り詰める等)。

## 4. 列挙の内部

- 列挙 (`list_recordings.py`) は pydtcpip の DLNA スタックで録画一覧を取得し、JSON で出す。資格情報は不要。
- ライブチューナーのチャンネルは DIDL 上 `object.item.videoItem.videoBroadcast` として現れるため除外する (pydtcpip CLI 自身の録画/チャンネルの区別と同じ)。
- 同一録画は all / ジャンル別 / 日付別の各コンテナに別々の object ID で現れる。録画の同一性は object ID 末尾の `pvr?id=` の値 (content_id) とし、代表エントリは `0/video/all/` のものを採る (docs/48 §2.2)。
- JSON の項目: タイトル、content_id と object ID、日時、長さ、チャンネル名、概要、ジャンル、res 一覧 (URL、protocolInfo、cleartextSize)、残コピー数 (`av:COGCount` 由来)、Move 可否。
- サーバーの選択は、発見プロファイル `sie_nasne` に一致するものを優先し、無ければ単一サーバーへフォールバックする。Windows / Mac でプロファイル名が `sie_nasne` でなく `nasne` と表示される現象は未確定のまま (docs/49 §6・§8.3)。

## 5. 設定の解決順序

### 5.1 パス類 (`resolve_config()`)

全てのパスは **引数 → 環境変数 → 既定値** の順で決まる。

| 項目 | 引数 | 環境変数 | 既定値 |
|---|---|---|---|
| 資格情報ファイル | `--credentials` | `RESCUE_CREDENTIALS` | `<base>/data/credentials.env` |
| データディレクトリ (srm.bin の置き場) | `--data-dir` | `RESCUE_DATA_DIR` | 資格情報ファイルのあるディレクトリ |
| 出力先 | `--out-dir` | `RESCUE_OUT_DIR` | `<base>/out` |
| ログ出力先 | `--logs-dir` | `RESCUE_LOGS_DIR` | `<base>/logs` |
| pydtcpip の場所 | `--pydtcpip-home` | `PYDTCPIP_HOME` | §5.2 の解決に委ねる |
| nasne のアドレス (手動登録) | `--host` | `RESCUE_HOST` | なし (SSDP で自動発見) |

### 5.2 `<base>` の互換動作と pydtcpip の解決

- `<base>` は、初期構築時の作業領域レイアウト (`LEGACY_ROOT`) がそのマシンに存在すればそちら、存在しなければツール自身のディレクトリになる。初期構築マシンでの既定パス (資格情報の絶対パス等) を変えないための互換動作である。
- pydtcpip 本体の解決は用途ごとに別系統:
  - **転送用 CLI** (`pydtcpip_cli()`): 環境変数 `PYDTCPIP_BIN` → `--pydtcpip-home` の `.venv/bin` または `.venv/Scripts` にある `pydtcpip` (`pydtcpip.exe`) → PATH 上の `pydtcpip` コマンド。
  - **列挙用 Python** (`pydtcpip_python()`): 環境変数 `PYDTCPIP_PYTHON` → `--pydtcpip-home` の venv の `python` (`python.exe`) → 実行中の Python で `import pydtcpip` が可能ならそのインタプリタ。
  - venv の実行ファイル置き場は POSIX の `bin/` と Windows の `Scripts/` の両レイアウトに対応する。

### 5.3 子プロセスの文字コード

- 子プロセスの環境には `PYTHONUTF8=1` と `PYTHONIOENCODING=utf-8` を加える。Windows の既定コンソール (cp932) や PowerShell のパイプでも、日本語タイトル (ARIB 外字を含む) が化けないようにするためである (経緯と癖は docs/49 §4.6)。

## 6. 手動登録の実装

- 発見だけを置き換える。pydtcpip の `DLNAClient.get_server(location)` (SSDP の LOCATION から MediaServer を作る公開メソッド) を使い、device description を直接取得する。以後の Browse は SSDP 経路と同一のユニキャスト HTTP である。
- アドレスの解釈 (`location_for_host()`): URL そのものならそのまま、`host:port` なら `http://<host:port>/`、ホスト名 / IP だけなら nasne の DMS ポート 58888 を補って `http://<host>:58888/` とする (SSDP 経路で得られる location と同一)。
- `fetch` / `fetch-all` は、一覧取得時に得た `server.location` を `stream --server` に渡す構造のため、手動指定の一覧から取得すれば転送先も同じ nasne になる。
- GUI のアドレス欄の入力値は、データディレクトリの `gui_settings.json` に保存され、次回起動時に読み戻される。保存されるのはアドレスのみで、資格情報には一切触れない。
- 動機 (SSDP マルチキャストがルーテッド経路を越えられない) と Mac / Tailscale での実走検証は docs/49 §8。

## 7. 実行時のデータレイアウト

```
out/
  listings/              列挙結果 JSON (実行毎)
  <content_id>-<タイトル>.ts       救出した復号済み TS
  <content_id>-<タイトル>.ts.json  そのタイトルのメタデータ + 取得記録
  manifest.json          救出済み一覧 (SHA-256 つき)
  SHA256SUMS.txt         sha256sum -c で検証できる形式
  .*.partial             転送途中のファイル (失敗時はここに残る。manifest には入らない)
data/
  credentials.env        資格情報 (本人のみが書く)
  srm.bin                初回 AKE 成功時に pydtcpip が自動保存する SRM
  gui_settings.json      GUI が保存する nasne アドレス (手動指定の値)
logs/                    実行ログ (pydtcpip の stderr を含む。範囲は §2.4)
```

- `data/` `out/` `logs/` はツール内の `.gitignore` で除外し、資格情報実物・SRM・救出済み TS が誤ってコミットされないようにしている (docs/49 §3)。

## 8. GUI の接続確認と転送速度表示 (2026-11-17 追加)

本人の Mac 実機検証での指摘 2 件 (転送速度が知りたい / IP を入れても繋がったか分からない) を受けて追加した。

### 8.1 接続確認

- 列挙スクリプト (`list_recordings.py`) に `--probe` モードを足した: サーバーの特定 (手動指定なら `DLNAClient.get_server` で device description を取得、空欄なら SSDP 発見) までで止め、Browse をせず、サーバー情報だけを JSON で返す。
- ドライバ側は `rescue.probe_server()` がそれを子プロセスで呼び、失敗時はスクリプトの stderr の最終行 (到達不能の内訳を含むメッセージ) を理由としてそのまま例外に載せる。
- GUI の「接続」ボタンはこの確認を実行し、結果をボタン行の表示に出す: 成功は「接続済み: <サーバー名> (<location>)」、失敗は「未接続: <理由>」。一覧取得が成功したときの表示も同じ形に揃えた。接続確認中は接続・一覧・救出の各ボタンを無効化する。
- SSDP モード (アドレス空欄) でも同じ表示になるため、「発見できたか」が曖昧にならない。

### 8.2 転送速度表示

- 進捗ポーリング (300 ms 間隔) が `.partial` のサイズをサンプルし (直近 10 秒分を保持)、進捗表示を「転送済み / 全体 (％) — X.X MB/s (平均 Y.Y MB/s)」の形にした。
- 主表示は直近 5 秒のサンプルからの移動平均 (300 ms 刻みの瞬時値はブレが大きく読めないため)、括弧内は fetch 開始以来の全体平均。両者が同じ値に丸まる場合は全体平均を省略する。
- MB/s は 10 進 (1 MB = 1,000,000 B) で、ツール README の転送時間の目安 (約 11 MB/s) と表記を揃えた。検証では有線 LAN の実 fetch で移動平均 11.0 MB/s・全体平均 11.3 MB/s (28 秒時点) と表示され、既知の実測と一致した。
