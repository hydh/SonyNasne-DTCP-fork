# DTCP-IP 録画救出ツール (dtcpip-rescue)

公式 FW の nasne に残っている録画を、DTCP-IP の正規の経路 (AKE + ストリーム受信)
で PC 側へ救出するツール。エンジン (AKE と復号) は
[pydtcpip](https://github.com/tsukumijima/pydtcpip) が担い、このツールは
列挙・転送ドライバ・保存・検証と、Tkinter 製の簡易 GUI を提供する。

**状態: 基本完成。** DR 録画・3倍録画のどちらも実機で AKE 完走・復号・
TS 検証 (サイズ一致、MPEG-TTS 同期バイト全数正常、SHA-256 一致) まで
実証済み。経緯と検証の詳細は [docs/48](../../docs/48_dtcpip_rescue_pipeline.md)
と [docs/49](../../docs/49_dtcpip_rescue_tool_and_windows.md) を参照。

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

ツー
...[truncated 4377 chars]