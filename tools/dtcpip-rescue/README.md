# DTCP-IP 録画救出ツール (dtcpip-rescue)

公式 FW の nasne に残っている録画を、DTCP-IP の正規の経路 (AKE + ストリーム受信)
で PC 側へ救出するツール。エンジン (AKE と復号) は
[pydtcpip](https://github.com/tsukumijima/pydtcpip) が担い、このツールは
列挙・転送ドライバ・保存・検証と、Tkinter 製の簡易 GUI を提供する。

DR 録画・3倍録画のどちらも、この経路で復号済み TS として取得できる。
取得した TS はサイズ・MPEG-TTS の同期バイト・SHA-256 で検証され、
manifest に記録される。解析と検証の記録は
[docs/48](../../docs/48_dtcpip_rescue_pipeline.md) と
[docs/49](../../docs/49_dtcpip_rescue_tool_and_windows.md) を参照。

## 鍵の分担 (重要)

- **鍵は利用者本人が `credentials.env` にだけ配置する。** このファイル以外に
  鍵を置く場所はない。チャットや他のファイル、コマンドラインに値を出さない。
- このツールのプログラム (CLI / GUI とも) は、鍵の値を **読まない・出さない・
  検証しない**。資格情報は pydtcpip 自身が env ファイルから読み込む。
  ドライバは pydtcpip を子プロセスとして起動する際、環境変数 `PYDTCPIP_*` を
  除去する。したがって資格情報の出所は `credentials.env` だけになる
  (pydtcpip の仕様では環境変数がファイルより優先されるため、その経路を塞いでいる)。
- ツールに鍵は同梱されない。リポジトリに入っているのは空テンプレート
  (`credentials.env.example`) だけ。
- GUI の「配置状態」表示も、ファイルの有無とサイズだけから判定し、値は読まない。

## 構成

```
tools/dtcpip-rescue/
  README.md              このファイル
  rescue.py              ドライバ (CLI: list / fetch / fetch-all)
  list_recordings.py     列挙 (資格情報なし)。pydtcpip の DLNA スタックで
                         SSDP 発見 + Browse し、録画一覧を JSON で出す
  rescue_gui.py          GUI (Tkinter、標準ライブラリのみ)
  credentials.env.example 資格情報の空テンプレート
  data/                  (実行時に作成) credentials.env と srm.bin
  out/                   (実行時に作成) 救出した TS と manifest
  logs/                  (実行時に作成) 実行ログ
```

`data/` `out/` `logs/` は `.gitignore` 済みで、コミットされない。

実行時のデータレイアウト:

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
```

## 転送方式について

pydtcpip の **`stream`** コマンドを使う。これは再生と同種の受信で、
**コピーを消費せず、nasne 側の状態も変更しない**。
pydtcpip の `move` / `receive` (ダビング) はコピーを消費するため、
このツールでは **使わない** (ドライバは呼び出さない)。

## 前提と pydtcpip の用意

- このツール自体は Python 3.10+ (標準ライブラリのみ)。
- pydtcpip は Python 3.13+ が必要。同梱しないので、別途用意して場所を教える。

pydtcpip の用意 (clone + venv の形が、このツールの想定レイアウト):

```
git clone https://github.com/tsukumijima/pydtcpip.git
cd pydtcpip
uv sync            # .venv ができる (uv が無い場合は venv + pip でも可)
```

ツールへの教え方は、引数 → 環境変数 → 既定値の順で決まる。

| 項目 | 引数 | 環境変数 | 既定値 |
|---|---|---|---|
| 資格情報ファイル | `--credentials` | `RESCUE_CREDENTIALS` | `<base>/data/credentials.env` |
| データディレクトリ (srm.bin の置き場) | `--data-dir` | `RESCUE_DATA_DIR` | 資格情報ファイルのあるディレクトリ |
| 出力先 | `--out-dir` | `RESCUE_OUT_DIR` | `<base>/out` |
| ログ出力先 | `--logs-dir` | `RESCUE_LOGS_DIR` | `<base>/logs` |
| pydtcpip の場所 | `--pydtcpip-home` | `PYDTCPIP_HOME` | `.venv` を含む pydtcpip のチェックアウト (POSIX は `bin/`、Windows は `Scripts\` のレイアウトに対応)。見つからない場合は PATH 上の `pydtcpip` コマンド、または実行中の Python から import できる pydtcpip を使う |

`<base>` は、従来の作業領域レイアウトが存在するマシンではそちら
(互換のための既定)、なければこのツール自身のディレクトリ。

資格情報ファイルは、空テンプレート `credentials.env.example` を
`data/credentials.env` にコピーし、利用者本人が値を書く
(変数は `PYDTCPIP_CERTIFICATE` と `PYDTCPIP_PRIVATE_KEY`、値は hex 文字列)。
ファイルのパーミッションは POSIX では 600、Windows では所有者のみに制限する。

## CLI の使い方

```bash
cd tools/dtcpip-rescue

# 録画一覧 (資格情報なしで動く)
python3 rescue.py list

# 1 件だけ取得 (ID は list の出力の content_id)
python3 rescue.py fetch --id <content_id>

# 全件取得
python3 rescue.py fetch-all
```

- 既に manifest にある録画はスキップされる。再取得は `--force`。
- `--timeout <秒>` で 1 件あたりの転送タイムアウトを指定できる (0 = 無制限)。
- 取得結果の検証は `out/SHA256SUMS.txt` で行える:

```bash
cd out && sha256sum -c SHA256SUMS.txt
```

## 転送時間の目安

marnux (有線 LAN) から `rescue.py fetch` で実測した値 (2026-11-17)。
転送速度はサイズ・種別 (DR / 3倍) によらず約 11 MB/s で、AKE は約1秒。
他に、一覧取得と取得後の検証 (SHA-256・マニフェスト更新) で
15〜20秒程度がかかる。計測の詳細は
[docs/49](../../docs/49_dtcpip_rescue_tool_and_windows.md) §7 を参照。

| 種別 | サイズ | 転送 | 合計 (呼び出し全体) |
|---|---|---|---|
| DR | 約3.0 GB | 約4分35秒 | 約5分 |
| DR | 約1.6 GB | 約2分26秒 | 約2分45秒 |
| 3倍 | 約577 MB | 約52秒 | 約1分10秒 |

所要時間の目安は「サイズ ÷ 11 MB/s + 約20秒」。

## GUI の使い方

GUI は CLI と同じ処理を画面から実行するためのもので、追加の依存はない
(Python 標準の Tkinter のみ)。前提 (pydtcpip の用意と資格情報ファイルの配置)
は CLI と共通。

### 起動

```bash
cd tools/dtcpip-rescue
# Linux / macOS
python3 rescue_gui.py
# Windows
py rescue_gui.py
```

- Linux ではディストリビューションによって `python3-tk` パッケージが
  別途必要な場合がある。
- macOS でも同じコードで動作するが、実機での動作確認は行っていない。

### 画面の構成

- **資格情報ファイルの欄**: `credentials.env` のパス表示と、配置状態の表示。
  「変更…」でファイルを選んでパスを切り替え、「フォルダを開く」でそのフォルダを
  エクスプローラ / Finder / ファイルマネージャで開く。
- **「録画一覧を取得」ボタン**: nasne を発見し、録画一覧を表に表示する
  (資格情報は不要)。接続できるとサーバー名がボタンの右に表示される。
- **録画一覧の表**: タイトル / 日時 / チャンネル / 長さ / サイズ / 残コピー。
- **「選択した録画を救出」ボタン**: 表で選択した録画 (複数選択可) を取得する。
- **進捗バー**: 転送中、取得済みサイズ / 全体サイズとパーセントを表示する。
- **救出済み (manifest) の表**: 保存済みの一覧 (タイトル / ファイル / サイズ /
  SHA-256 先頭 16 桁 / 検証結果)。「ハッシュ検証」ボタンで保存済みファイルの
  SHA-256 を manifest と再照合する。
- **ログ欄**: 処理の進行と結果が表示される。

### 操作の流れ

1. 起動したら、まず上部の **配置状態** を確認する。未配置の場合は、
   表示されているパスの場所に `credentials.env` を置く
   (「フォルダを開く」がそのフォルダを開く)。置き場所を変えたい場合は
   「変更…」でファイルを選ぶ。
2. 「録画一覧を取得」を押す。
3. 表から救出したい録画を選び、「選択した録画を救出」を押す。
   進捗バーとログで進行を確認する。
4. 完了すると manifest の表に結果が追加される。必要なら「ハッシュ検証」で
   保存内容を再確認する。

### 配置状態の見方

配置状態は、ファイルの有無とサイズだけから判定している (値は読まない)。

- `未配置 (ファイルがありません)` — 指定パスにファイルがない。
- `未配置 (空テンプレートのまま)` — ファイルはあるが空テンプレートと同等。
- `配置済み` — テンプレートより大きいファイルがある (サイズからの推定)。

### 注意点

- GUI も CLI と同じく、鍵の値を読まない・出さない・検証しない。
- 取得の実行中は、一覧取得と取得のボタンが無効になる。
- 既に manifest にある録画はスキップされる。再取得したい場合は CLI の
  `fetch --force` を使う。

## Windows での注意

- コンソールが cp932 の環境でもタイトル等が文字化けしないよう、ツールは
  pydtcpip の子プロセスへ `PYTHONUTF8=1` を渡して UTF-8 で処理させる。
- PowerShell 5.1 のリダイレクトは UTF-16LE で書かれるため、`list` の JSON を
  ファイルに残す場合はエンコーディングに注意する
  (例: `Out-File -Encoding utf8` を使う)。
- pydtcpip の venv は Windows の `Scripts\` レイアウトに対応している。
