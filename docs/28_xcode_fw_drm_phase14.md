# XCode ファームウェア DRM モジュール解析 第14段

2026-11-15。第13段 ([docs/27](27_xcode_fw_drm_phase13.md)) の残件のうち本命 1 件 — OPEN_GENERIC_STREAM (FN=25) の主 FW 側ハンドラ同定と、録画保存の GENERIC-AES セッションへの鍵装填経路の特定 — に専念する段。前回の試行は成果物を残さず終了したため、本段は骨組みと調査計画を先にコミットし (進捗のアンカー)、区切りごとに中間コミットを打ちながら進める。

手法は第9段の M1–M6 を踏襲 (Ghidra 実読を主とし、GPL ドライバ一次資料で配送を裏付ける)。素材は開発側作業領域 `2026-11-13-fw-drm/phase14/` (Ghidra プロジェクト `ghp14` = 第2 FW、`ghp14m` = 主 FW、いずれも phase13 プロジェクトの複製)。アドレス表記は各イメージのロードベース基準 (主 FW = 0、第2 FW = 0xB00000) で、ファイルオフセットと一致する。

## 1. 課題と判定したい問い

**課題**: FN=25 (OPEN_GENERIC_STREAM) の主 FW (procIdx=0) 側ハンドラを同定し、そのセッション生成処理を実読して、GENERIC-AES セッションの鍵がどこから来るかを追う。

判定したい問い:

- (a) 鍵装填は鍵ストアスロット経由か。経由するなら、パケット/セッション構造のどの欄がスロット番号を持つか。
- (b) SCRAMBLER 経路と鍵素材を共有するか (§49 トークンが投入されるスロットと GENERIC セッションの鍵の関係)。
- (c) 鍵の出所は、ホスト供給・トークン解決・OTP 由来・エンジン内部生成のどれか。

副次的に、§49 トークン (SCRAMBLER 経由でスロットへ逐語投入される control_words) と GENERIC セッションの関係が事実として取れたら対応づけ、E2 (docs/02 §12) 失敗の候補 (iii) — 「`.dat` の暗号化そのものは GENERIC-AES セッション側の内部処理であり、録画時の SCRAMBLER 呼出しは別目的である可能性」 (docs/27 §4.3 で未判定) — の判定に繋がる所見があれば明記する。

## 2. 前提 (確定済み事項)

- SCRAMBLER 経路は投入・消費の両側で閉じている: 鍵ストアスロット (128 スロット、共有域 +0x1824/+0x1828/+0x182C) へホスト供給 CW が逐語投入され、消費はエンジン (HW) がスロットを直接参照する。FW 側の変換は無い ([docs/25](25_xcode_fw_drm_phase11.md) / [docs/26](26_xcode_fw_drm_phase12.md))。
- 製品構成のホスト SCRAMBLER は第2 FW 実装 `0xBF894C` (procIdx=6) が受ける。主 FW の `0x22F9E0` は proc0 ローカル文脈用の同型実装 ([docs/27](27_xcode_fw_drm_phase13.md) §3)。
- 録画保存の実形態は SECUREDTS (復号) + GENERIC-AES (generic_mode=0x4000、req_size=0xFC00)。鍵コマンド 0x113/0x114 は録画ログに皆無 (docs/02 §10)。
- OPEN_GENERIC_STREAM は FN=25、procIdx=0 = 主 FW 宛 (GPL 一次資料 txcdev.c)。パケット `cmd_open_generic_stream` とドライバ API `param_opengeneric` の双方に鍵欄は無い。欄として存在するのは generic_mode、DMA バッファ情報、card_type、共有入力バッファ、`generic_session_handle` (AACS 認証で交渉したセッション鍵へのハンドル)、drmflags、dma_direction、scrambling_ctrl_flags、`rng_data[32]` (DTCP 用予約)。録画時の実測ではゼロ初期化後に generic_mode / req_size / 共有入力バッファサイズのみが刻まれ、残りは全て 0 (docs/27 §4.1、docs/02 §10.2)。
- §49 トークンの行き先は「SCRAMBLER 要求の control_words 欄 → 状態ブロック語 `[handle+0x8B0]` が指す鍵ストアスロットへの逐語投入 (先頭 16 バイト、2 スロット分)」まで具体化している (docs/27 §4.3)。
- SECUREDTS は専用 mhcmd を持たず OPEN_STREAM (FN=8、procIdx=0) のペイロード内のストリーム種別で表され、鍵素材は含まない (docs/27 §4.1)。

## 3. 調査計画 (入口)

1. **主 FW の中央メールボックスハンドラの同定**: 第2 FW の中央メールボックスハンドラ `0xC74BBC` (オブジェクト登録コールバック経路 + FunctionNumber 直接振り分けの 2 経路、docs/25) と対になる主 FW 側実装を、主 FW のメールボックス受信処理・FN 振り分け構造から辿る。
2. **FN=25 の分岐先の特定**: 振り分け表/分岐列から FN=25 に対応するハンドラ入口を特定する。
3. **ハンドラとセッション生成処理の実読**: セッション構造の確保・初期化、鍵関連欄 (スロット番号、セッション鍵ハンドル等) の読み書きを追う。
4. **鍵装填の追跡**: ハンドラ以降の処理に、鍵ストア窓 (共有域 +0x1824 台) へのアクセス、状態ブロック +0x8B0 台の参照、OTP 読み出し経路への接続があるかを実読と census で確認する。
5. **GPL 一次資料との照合**: txc_open_ts.c / txcdev.c の GENERIC 経路と `cmd_open_generic_stream` の配送実装で、FW 側の受け口の形を裏付ける。

## 4. 結果

(調査中。以後の節に追記する)

## 5. 判定

(未記入)

## 6. 残件

(未記入)

## 7. 方法・素材メモ

- 作業領域: 開発側 `2026-11-13-fw-drm/phase14/`。Ghidra プロジェクトは phase13 の複製 (`ghp14` / `ghp14m`)、実行ハーネスは `run14.sh` (analyzeHeadless、`-noanalysis` で既存解析結果を使用)。使用スクリプトは phase13 から引き継いだ Dump10.java / ScalarScan10.java / DispScan13.java / RangeDump13.java / RefTo13.java 等。
- capstone は対象範囲で Ghidra と復号が合わない既知の問題があるため (docs/27 §7)、本段も Ghidra を使用する。
