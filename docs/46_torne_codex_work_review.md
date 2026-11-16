# 46 先行作業 (他 AI ツール) の torne → pydtcpip 解析成果物の精査

対象: 本人が別の AI ツールに依頼した「torne mobile の資格情報を pydtcpip の `DeviceCredentials` として取り出す」作業の成果物一式 (zip で提供され、作業は資格情報の取得に至る前に打ち切られた)。本書はその精査記録であり、先行作業の到達点、docs/45 §8 の未確定事項への対応状況、docs/44 への訂正、本精査で裏取りした確定事項を記録する。

状態: **先行作業は有効な証明書・鍵ペアの取得に至っておらず、`credentials.env` は空のテンプレートのままである (本精査で実物確認)。** 先行作業の report は作業途中で本リポジトリの docs/45 を取り込んで解釈を更新しており、最終的な位置づけ (cxml は DEWEY の DAL 用、AVBase は資格情報源を持たない、PLAY ライセンスは権利管理) は docs/45 と一致する。先行作業が新たに持ち込んだ材料は、(a) Frida による動的観測の記録、(b) 再インストール〜購入復元の実機観測、(c) Android Java 層 (jadx) の読解、(d) 本精査で裏取りした静的確定事項 (docs/44 の文字列件数の訂正、LoadDtcpIpUtility の呼出し元の特定) である。docs/45 §8 の未確定事項は、本段でも全て未確定のままである (進展の内訳は §6)。

## 1. 精査の範囲と方法

- 対象 zip: `nasne-apk-pydtcpip-analysis.zip` (498,301,018 バイト、SHA-256 `6da6b6dba701f57a4c46e97c58327719eb7ab6f05b73e661b79631fc5b477ba3`)。構成は `artifacts/` (report.md、スクリプト 7 本、credentials.env)、`input/` (Android 版 XAPK、iOS 版 IPA、SE1 のアプリコンテナとキーチェーン書出しのコピー)、`work/` (展開したバイナリ、逆アセンブル、jadx 出力、pydtcpip の clone、監査・捕捉の結果 JSON 群)、`tools/` (jadx 本体)。
- 本精査の作業は、成果物の読み取りと、既存材料 (バイナリ実物・逆アセンブル・コンテナ実物・保存 JSON) による静的な裏取りに限る。**資格情報の抽出を目的とするスクリプト (decrypt 系・watch 系) の実行、pydtcpip の AKE 実行、入力コンテナへの新規の復号試行は行っていない。**
- 格付け: 〔裏取り済み〕= 本精査で実物を直接確認したもの。〔先行観測〕= 先行作業の動的観測の記録で、観測手法 (何を数え、何を読まないか) はスクリプトのコードで確認したが、結果そのものは再検証していないもの。〔先行主張〕= report の記述のみで、結果の保存物が zip 内に無いもの。
- 先行作業と docs/45 の範囲の違い: docs/45 は静的解析に限定し、メモリ捕捉を行わない方針だった。先行作業は Frida による実機動的観測に加え、実行時鍵の捕捉と DB ページ平文の捕捉を試行した。その帰結は §3 の通りで、鍵素材も DB 平文も得られていない (保存サマリで確認)。本精査はこれらの試行を繰り返さない。
- 先行 report のうち pydtcpip が必要とする nasne 側 API の形状整理は docs/32・37 の記録の再整理であり、先行作業による実機測定は行われていない (外部接続・nasne 接続なし、と report に明記)。

## 2. 裏取り済みの確定事項

### 2.1 Android の WebAPI パス文字列は 65 件 (docs/44 の訂正)

先行作業の `reproduce.py analyze` は正規表現 `(?:config|recorded|schedule|status|chEpg)/[A-Za-z0-9]+` で 3 ライブラリを走査し 65 件を数えた。本精査で同じ正規表現の走査を独自に再実行し、内訳まで一致を確認した: **libPvrMain_plus.so 単体で 65 件**、libPvrBgApp.so に 13 件 (サブセット、docs/44 §2.3 と一致)、libAVBase.so に 0 件。

これにより docs/44 §2.1 の「iOS のみ: 2 件 (`schedule/reservedListGet2`、`status/liveStreamPCRGet2`)。いずれも Android の文字列には裸名でも存在しなかった」は、**文字列レベルで誤り**だったことが確定した。両文字列は libPvrMain_plus.so 内に存在する。数え直しでは、Android の 65 件は iOS の 62 件を全て含み (共通 62)、Android のみは chEpg 群 3 件のみ、Vita 2.02 の 56 件も文字列レベルでは全て含む形になる。docs/44 本文と README 索引には本段で訂正注記を入れた (§7)。

なお、両文字列が Android で実 endpoint として呼ばれるか (呼出し参照の有無) は先行作業・本精査とも追跡しておらず、未確定である。先行 report もこの点を正しく未確定としていた。

### 2.2 LoadDtcpIpUtility の直接呼出し元は AVBase 内の 1 箇所のみ

先行作業の動的観測 (§4) では、AVBase の `LoadDtcpIpUtility` (実体 `0x4f9fc`、docs/45 §2.1) の呼出し元リターン位置が `AVBase+0x4f9e8` と記録されていた。本精査で先行作業の逆アセンブル (`work/avbase.disasm.txt`) を確認したところ:

- `0x4f9e4` に `bl 0x4f9fc` があり、直後の `0x4f9e8` が記録された戻り先と一致する。
- この `bl` は AVBase 全体で `0x4f9fc` への**唯一の直接呼出し**である。
- 呼出しを含む関数は `0x4f96c` から始まる AVBase 内部の関数 (引数 2 個を受け、フレームワーク側の初期化系の呼出しを連ねた末尾で Load を呼んで 1 を返す形) であり、アプリ層 (torneplus) からの直接呼出しではない。

docs/45 §2.1 の構造理解 (Load / Activate はメッセージ機構への要求組立て) と整合し、Load が AVBase 自身の初期化の流れの中で駆動される形であることが静的に裏付いた。先行観測の「起動時に各窓 1 回だけ発火し、呼出し元は AVBase 内」という記録とも一致する。

### 2.3 Android の storeMoveParams (GAE `key` 応答の機能スコープ付き消費)

先行作業は jadx 出力で `AppBillingHelper.storeMoveParams(String, String)` (native) の存在を確認した。本精査で jadx ソース (`com/playstation/tornemobile/AppBillingHelper.java`) を直接確認した:

- 購入適用の処理は、応答 JSON に `key` があれば、その `key` オブジェクト全体を文字列化して `storeMoveParams` へ渡す。
- 製品が `torne.function.move` で購入適用中の場合、`key` の格納が済んでいないと例外になる。すなわち move (書き出し) 機能では `key` の受領・格納が必須の前提になっている。
- native 側が `key.id` と `key.data` を読むという点は先行 report の記述であり、本精査では native 実読まで行っていない (〔先行主張〕の格)。

これは docs/45 §5 (iOS 側でライセンス応答の `key` フィールドが keyid として管理される) と並行する観測で、GAE の `key` 応答が「機能 (書き出し) にスコープされた鍵材料の配布」であることを Android 側でも示す。先行作業が「LAN 再生の資格情報源とは確認できない」と分類した判断は妥当であり、docs/45 §7 の「DEWEY/DAL 資格情報の主たる消費者は書き出し機能」という推論を補強する材料になる。ただし iOS の `StoreDtcpipKey` の実装同定には至っていない (§6)。

### 2.4 再インストール〜購入復元の帰結状態 (実物確認)

先行作業は、再インストール直後の torne (初回起動前) のコンテナ保存、初回起動、購入復元、復元後コンテナの再保存を行った。本精査では復元後コンテナの実物 (`work/post-restore-container`) を確認した: **48 ファイル、合計 5,081,642 バイト**。`Documents/LICENCEDIR` には TRIAL 3 件 (`SCE_001_TorneBlackTRIAL`、`SCE_005_WoodyTRIAL`、`SCE_905_PLAYTRIAL`) と正規版 `SCE_905_PLAY` 1 件があり、全て 464 バイトで docs/45 §3 の形式と一致する。`Documents/Manage` には `PvrContent.db`、`PvrOperationLog.db`、`PvrGameConfig.cxml`、`PvrSaveData.cxml` 等が再生成されていた (ファイルの存在とサイズのみ確認し、内容は読み出していない)。

### 2.5 入力コンテナと docs/38 スナップショットの同一性

zip の `input/` に含まれる SE1 コンテナの LICENCEDIR 4 ファイルは、同梱の実機スナップショット (`input/ios/live_licencedir`) と**バイト単位で同一**だった (本精査で照合)。入力コンテナは docs/38 の SE1 コピーの系統であり、docs/38 以降 LICENCEDIR が不変だったという docs/45 §3.1 の観測とも矛盾しない。

### 2.6 キーチェーン書出しと URL キャッシュ (監査結果の確認)

- キーチェーン書出しは 4 項目 (本精査では項目数と値のバイト長のみを確認し、値そのものは記録しない): torne ストレージ項目 (service = `torne moible`、account = `com.playstation.tornemobile.storage`、docs/38・45 の向き) が 16 バイト、DUID 系項目が 50 バイト、WebCrypto 系項目が 24 バイト、Telepathy の identifierForVendor 項目が 16 バイト。先行 report の記述と一致する。先行作業の初期草稿は torne 項目の service/account の向きを逆に読んでおり、docs/38 の向きで訂正済みであることが report に明記されていた。
- URL キャッシュ監査 (先行作業の保存 JSON `ios-audit.json` で確認): request blob に `mobileid` 文字列を含む記録が 1 件あるが、応答本文は 72 バイトで `encrypteddata` 等のライセンス応答の標識を含まない。「ライセンス応答を保存したものとは確認できない」という先行作業の判定は保存物と一致する。
- StoreKit receipt は存在のみ確認 (5,237 バイト、内容は先行作業・本精査とも読み出していない)。IPA の SHA-256 (`576e9fba…`) は docs/21 の記録値と一致した。XAPK の SHA-256 (`f032445e…`) は docs/44 の記録値と一致した。

## 3. 捕捉試行の帰結 (先行作業の保存サマリで確認)

先行作業のうち、資格情報の取得を直接狙った 2 本の実行結果が `work/decrypted/` に保存されていた。いずれも成果物は得られていない。

1. **CXML 実行時鍵の捕捉** (`decrypt_cxml.py`): torneplus の CXML 文脈準備関数 (`+0x429EF0`) にフックを掛け、成功時に得られる AES 鍵で手元の保存 CXML (`PvrSaveData.cxml`、同 backup、`PvrGameConfig.cxml`) を docs/36 の形式で復号し、平文から証明書・鍵ペアを走査する設計。保存サマリ (`decryption-summary.json`) ではフック成立・アドレス一致まで確認されたが、**観測窓内で当該関数の呼出しは 0 回**で、鍵は得られず、3 ファイルとも復号未成立 (平文先頭の SHA-256 照合で棄却)、証明書 0 件だった。
2. **DB ページ平文の捕捉** (`decrypt_db_pages.py`): torneplus の AES-CBC 復号ラッパ (`+0x380E24`) の入出力を捕捉し、入力 DB (`PvrContent.db`、`PvrOperationLog.db`、`initialContent.db`) のページ平文を再構成する設計。保存サマリ (`db-decryption-summary.json`、`db-page-manifest.json`) では **1,530 件の復号呼出し (呼出し元は全て torneplus+0x5b180、出力の大半は 4,096 バイト) を捕捉したが、入力 DB への対応付けは 0 件、SQLite マジックを持つ出力も 0 件**で、部分平文ファイルは生成されなかった。捕捉された復号は DB ページ向けではなかったと読めるが、その用途は未同定である (§8)。
3. `trace_storage_crypto.py` (暗号プリミティブの入口回数と呼出し元の計測) は、成果物内に結果の記録が残っていない。上記 1 のフック位置の特定過程とみられるが、記録としては扱えない。

## 4. 先行観測 (動的観測の記録)

先行作業の `watch_dtcp_flow.py` は、DTCP/鍵経路の 12 入口について**入口の回数と (Load/Activate のみ) 呼出し元オフセットだけ**を数える実装である (引数・バッファ・メモリを読まないことは本精査でコードを確認した)。対象は torneplus の GAE key check (`0x42953c`、docs/45 §5 の `opDtcpipKeyCheck`)、PvrBgApp の KeyManager Initialize (`0x12eb8`)、組立て関数 (`0x71814`)、証明書ロード (`0x71928`)、提供オブジェクト登録 (`0x9c500`)、組立て補助 (`0xa2964`)、資産プロバイダ (`0x1b5090`)、資産ローダ (`0xc5e0`)、AVBase の Load (`0x4f9fc`)、Activate (`0x50258`)、Auth 状態 (`0x9efec`)、メッセージハンドラ (`0xa0a5c`)。フック前に実機メモリの先頭 16 バイトと取得バイナリを照合する手順も含まれる (最初の 11 箇所は 11/11 一致、追加した KeyManager export は別途一致を確認、と report にある)。

記録された結果:

- アタッチ方式 (本人が開始した再生の最中、120 秒と 75 秒の 2 窓): 12 件全て 0 回。
- spawn 方式 (停止状態から起動してフック後に再開、120 秒と 90 秒の 2 窓): `LoadDtcpIpUtility` のみ各窓 1 回 (呼出し元は §2.2 の AVBase 内 1 箇所と一致)、他の 11 件は 0 回。KeyManager Initialize、組立て関数 `0x71814`、提供オブジェクト登録 `0x9c500`、資産ローダ/プロバイダ、GAE key check は、起動から再生操作を含む窓を通じて発火しなかった。
- `watch_avbase.py` (CCCrypt / SecItemCopyMatching / SecIdentityCopyCertificate / SecCertificateCreateWithData の AVBase 発呼出しの計測) は、再生中 90 秒の窓で 4 API 全て 0 回と report に記録されている (結果の保存物は zip 内に無い)。
- 初回起動時のファイル操作は `fs_usage` の実時間出力で観測され、起動直後に `Documents/LICENCEDIR` が作成され TRIAL 群が書き込まれた (保存を試みたログは空だったため時系列の保存物は無い。帰結状態は §2.4 で実物確認済み)。

**この観測の射程 (重要)**: 先行 report 自身も明記する通り、観測窓が再生開始の遷移を完全に捕捉した証明はなく、特に AVBase の Auth 状態・メッセージハンドラまで 0 回という結果は、入口の選定が実際のストリーミング経路とずれていた可能性を排除しない。したがって本観測は「DEWEY/DAL 経路が再生時に使われないことの積極証拠」ではなく、「起動〜再生の観測範囲では、DEWEY 側の資格情報入口 (KeyManager・組立て・登録・資産読込) の発火は一度も観測されなかった」という範囲の記録として扱う。docs/45 §8 の未確定事項 1–3 の判定は変えない (§6)。

## 5. 先行主張 (保存物の無い記録)

- **DTLA 証明書の全件走査**: iOS 入力 61 ファイル (計 82,643,241 バイト) とキーチェーン書出しの復号値について、証明書形式の候補位置 67,673 箇所を pydtcpip の署名検証 (`verify_certificate`) に通し、有効な 88 バイト証明書は 0 件だった、と report にある。走査の手法 (候補パターン、生バイトと hex 復号値が対象で、暗号化・圧縮された内部は対象外) は `reproduce.py` のコードで確認した。ただし実行結果の JSON は zip 内に保存されておらず (同梱の `ios-audit.json` は走査項目を含まない版)、数値は report の記録として扱う。この結果は「このコピーの平文的な範囲に正規証明書は無い」ことを示すに留まり、暗号化された内部に資格情報が無いことの証明ではない (先行 report も同旨を明記している)。

## 6. docs/45 §8 未確定事項への対応状況

| # | docs/45 §8 の未確定事項 | 本段での状況 |
|---|---|---|
| 1 | LAN 再生時の AKE 駆動経路 | **未確定のまま。** 進展として、LoadDtcpIpUtility の呼出し元が AVBase 内 1 箇所 (初期化系の関数) であることを静的に特定 (§2.2)。先行観測では DEWEY 側入口の発火は観測されなかった (§4、射程の注記つき)。セッション鍵が Auth バッファへ届く経路は依然不明 |
| 2 | 第 2 供給路の提供オブジェクト実体と `0x9c500` の実行条件 | **未確定のまま。** 先行観測の窓 (起動〜再生) では `0x9c500` の発火は観測されなかった。実体の同定はなし |
| 3 | 組立て関数 `0x71814` の間接呼出しの有無と実行条件 | **未確定のまま。** 同上、観測範囲では発火なし。静的な間接呼出しの有無は変わらず不明 |
| 4 | DAL アイテム 1 への投入の成立条件、`#13` の内部構造 | **未確定のまま。** 実物の `PvrAssetData.cxml` は今回の入力にも存在せず、新しい材料なし |
| 5 | `StoreDtcpipKey` / `DtcpIpUnpackAndStoreParams` の実装と呼出し元 | **未確定のまま。** Android 側で同種の「`key` 応答を native へ格納する」処理 (storeMoveParams、書き出し機能向け) を同定したが (§2.3)、iOS の当該関数の実装同定ではない |
| 6 | SE1 の正規版 `SCE_905_PLAY` が GAE 経由かローカル変換か | **未確定のまま (観測の追加あり)。** 再インストールした素の状態では初回起動時に TRIAL のみが生成され、正規版は購入復元の後に現れた (§2.4)。復元経路と整合するが、復元を契機とするローカル変換の可能性は形式的に残る |
| 7 | Android 版の対応関係 (LICENCEDIR 相当、第 2 供給路) | **大部分は未確定のまま。** LICENCEDIR 相当の権利管理と第 2 供給路は Android 側では先行作業も調査していない。一方で WebAPI 文字列集合の訂正 (§2.1) と storeMoveParams の同定 (§2.3) は Android 側の新規確定事項 |

## 7. 既存文書への訂正 (本段で反映)

- docs/44 §2.1: 「iOS のみ: 2 件…Android の文字列には裸名でも存在しなかった」の記述と 63 件という件数について、本書 §2.1 の数え直し (65 件、iOS の 62 件を全て含む) に基づく訂正注記を本文末尾に追加した。README 索引の 44 の行の要約も同じ内容で更新した。両文字列が実 endpoint として呼ばれるかは未確定のままである。
- docs/45 §8 の未確定事項そのものへの訂正はない (§6 の通り全て継続)。

## 8. 残る未確定事項

- docs/45 §8 の 1–7 (§6 の表の通り全て継続)。
- 先行作業が捕捉した torneplus+0x5b180 からの 1,530 件の AES-CBC 復号 (§3-2) の用途。DB ページ向けでなかったことだけが分かっている。
- `schedule/reservedListGet2` と `status/liveStreamPCRGet2` が Android で実 endpoint として呼ばれるか (呼出し参照の追跡)。
- 先行観測 (§4) の再現性。観測窓と入口選定を変えた再観測は行われていない。

## 9. 作業素材

- 展開先: `SonyNasne-DTCP.work/2026-11-16-codex-zip-review/` (zip 本体と入力コピーは改変していない)。
- 本精査で裏取りに使った先行成果物: `work/avbase.disasm.txt` (AVBase 逆アセンブル)、`work/jadx/sources/com/playstation/tornemobile/AppBillingHelper.java`、`work/post-restore-container/` (復元後コンテナ実物)、`work/decrypted/decryption-summary.json` / `db-decryption-summary.json` / `db-page-manifest.json`、`work/ios-audit.json`、`work/final-apk-audit.json`、`input/ios/keychain.json` (項目数と値の長さのみ参照)、`artifacts/report.md` とスクリプト 7 本 (全て読み取りのみ、実行していない)。
