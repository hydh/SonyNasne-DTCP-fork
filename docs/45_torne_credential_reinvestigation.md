# 45 torne mobile の資格情報プロビジョニング前提からの再調査 (AVBase 側スタック・LICENCEDIR・DEWEY 残件の決着)

対象: torne mobile v1.50 (iOS 版 `torneplus` / `AVBase` / `PvrBgApp`、Android 版 `libAVBase.so` / `libPvrBgApp.so` / `libPvrMain_plus.so`)。docs/33–36・38 の前提を検証し直す段。

状態: **「録画再生に `PvrAssetData.cxml` が必要」という従来の理解は棄却した。** 根拠は次の 3 点の実測である。(1) DTCP-IP の AKE 暗号 (専用楕円曲線のドメインパラメータ) は 3 バイナリ中 `PvrBgApp` (DEWEY) にのみ存在し、プレイヤ側 `AVBase` と本体 `torneplus` には 6 種のバイト表現すべてで存在しない。(2) `AVBase` の CDtcpIp スタックは証明書・鍵を自前では保持せず (ファイル・キーチェーンへのアクセスは libcurl の TLS 用のみ)、認証データはプロセス内メッセージで注入される構造である。(3) 実機 (docs/38) では cxml が生成されないまま再生が成立し、代わりに初回起動時に `Documents/LICENCEDIR/` へ視聴ライセンスのファイル群が生成されていた。本書では LICENCEDIR の書き手・形式・消費者、DEWEY 側の第 2 供給路 (docs/33 §5.2) の構造、機能ごとの資格情報対応表を確定範囲で記録する。鍵素材の抽出・復号による取得・メモリ捕捉は本段でも行っていない (形式構造の同定まで)。

## 1. 解析方法

- 静的解析のみ。対象は手元のファイル (展開済み IPA の 3 バイナリ、Android 版 APK のネイティブライブラリ 3 本、実機コンテナスナップショット 2 点 + バックアップ抽出コンテナ 1 点)。
- 逆アセンブル実読 (llvm-objdump)、radare2 の `aaa` + `axt`、自作スキャナ (ADRP+ADD/LDR のデータ参照走査、BL 宛先集計、ポインタ走査、定数パターン走査)。
- 観測 (逆アセンブル・ファイル実物で直接確認したもの) と推論 (構造からの解釈) は本文中で区別する。未確定事項は §8 に集約する。

## 2. AVBase の CDtcpIp スタック (調査項目 1)

### 2.1 構成 (観測)

`AVBase` 内の DTCP-IP 関連クラスは RTTI 名のみが残る (シンボルはストリップ済み)。

| クラス | typeinfo | 役割 (構造からの同定) |
|---|---|---|
| `CDtcpIpWrapperImpl` | `0x27cf30` | 集約オブジェクト (約 0x1100 バイト、専用スレッド `CDtcpIpWrapperThread` を持つ) |
| `CDtcpIpAuth` | `0x27cc88` | 認証状態 + 約 0x104 バイトの内蔵バッファ (オブジェクト約 0x120 バイト) |
| `CDtcpIpStreaming` | `0x27cce8` | ストリーミング本体 (約 0x868 バイト) |
| `CDtcpIpHttp` | `0x27ce88` | HTTP 担当 (0x18 バイトの小物) |
| `CDtcpIpMemory` | `0x27ccb8` | バッファ管理 |
| `CDlnaClientDtcpIpUtilityWrapper` | `0x249e90` | 上位向けユーティリティ API のクライアント側 |

- `CDtcpIpWrapperImpl` のコンストラクタ (`0xa0800`) は Auth (+0x10)、Streaming (+0x130)、Http (+0x998)、Memory (+0x9b0) 等のサブオブジェクトを構築するだけであり、ファイル・キーチェーン・ネットワークからの資格情報取得は行わない。
- ユーティリティ API (`LoadDtcpIpUtility` 実体 `0x4f9fc`、`ActivateDtcpIp` `0x50258`、`CancelActivateDtcpIp` `0x50450` 等) は、名前付きリクエストオブジェクトを組み立ててシングルトンのサービスオブジェクト (「Ac」フレームワークのタスクメッセージ機構、実関数表 `0x27b330`) へ番号付きメッセージとして送る形である。`Load` / `Activate` のいずれも証明書・鍵サイズのバッファを引数に取らない (`Activate` が受け取るのはポインタ 2 個で、コールバック登録に使われる)。
- `CDtcpIpAuth` のメソッド群 (`0x9efec`–`0x9f0f8`) は小さな状態機械であり、そのデータは WrapperImpl のメッセージハンドラ (0xa0a5c–0xa0e00) から、受信メッセージのペイロード (ポインタ + 長さ + 付随値) として渡される。CDtcpIp コード群 (0x9e000–0xa1100) のデータ参照は vtable・GOT・トレース文字列・bss 大域と倍精度定数 1 個のみで、**埋め込みの証明書・鍵 blob への参照は存在しない**。

### 2.2 AKE 暗号の所在 (観測・積極的な所在確定)

DTCP-IP の AKE で使う専用楕円曲線 (160 ビット) のドメインパラメータ (p / a=p−3 / b / 位数 / 生成点 Gx・Gy) を、バイト列の 6 表現 (BE、全体反転、4 バイトリム反転、8 バイトリム反転、その複合 2 種) で全バイナリ走査した。

| バイナリ | 結果 |
|---|---|
| iOS `PvrBgApp` | **存在** (BE バイト列、20 バイト × 6 フィールドの表 @0x35eb18) |
| iOS `AVBase` | 全表現で不在 |
| iOS `torneplus` | 全表現で不在 |
| Android `libPvrBgApp.so` | **存在** (BE @0x69f28) |
| Android `libAVBase.so` | 不在 |
| Android `libPvrMain_plus.so` | 不在 |

あわせて、`AVBase` には AKE のプロトコル語彙 (dtcp.com 系ヘッダ、AKE メッセージ名) が存在しない (対照的に `PvrBgApp` には SdiReqCHALL / SdiRespEXKEY 等が揃う)。`AVBase` の `SecItemCopyMatching` 利用は libcurl の SecureTransport 実装 (クライアント証明書のキーチェーン検索、呼び出し元 `0x23a1b8` が curl の SSL エラー文字列を参照) であり、DTCP とは無関係である。`AVBase` は `dlopen` / `dlsym` も `PvrDtcpIp*` シンボルも import しない。

### 2.3 結論 (項目 1)

- **AKE の ECC 演算は本アプリ内で DEWEY (`PvrBgApp`) のみが実装する** (定数の所在による確定)。プレイヤ側スタックは AKE 暗号を持たず、証明書・秘密鍵の保管場所も持たない。
- AVBase 側の構造は「ストリーミングとコンテンツ復号 (AES) の機械 + メッセージで注入される認証バッファ」であり、セッション確立そのものは外部 (同一プロセス内の DEWEY、torneplus のプレイヤ層が仲介) で行われる設計と整合する。ただし、その制御経路 (誰が DEWEY の AKE を駆動し、セッション鍵がどう Auth バッファへ届くか) は静的には同定できなかった (§8)。
- docs/21 §4.2・§8 / docs/33 §12 で「未調査」とされた AVBase の資格情報源については、「AVBase 自身は資格情報源を持たない」が確定した、と読み替えるのが正確である。

## 3. LICENCEDIR の仕組み (調査項目 2)

### 3.1 実物 (観測、docs/38 のスナップショット実物)

- 場所: `<アプリコンテナ>/Documents/LICENCEDIR/`。ファイル名は `SCE_<番号>_<製品名>[TRIAL]_<16 文字の小文字>.dat`。
- 実機 (SE1) 初回起動時の生成: 起動直後 (12:47:58) に TRIAL 3 件 (`SCE_001_TorneBlackTRIAL`、`SCE_005_WoodyTRIAL`、`SCE_905_PLAYTRIAL`)、22 秒後 (12:48:20、視聴機能の購入復元を行ったセッション内) に `SCE_905_PLAY` (正規版) が追加された。以後、ペアリング・ライブ視聴・録画再生・ペア更新を経ても **内容・更新時刻とも不変** (スナップショット 2 点の差分なし)。
- メイン端末のコンテナでも同構成 (TRIAL 群はインストール時、正規版 `SCE_905_PLAY` は約 1.5 日後 = 購入時刻と整合)。
- 全ファイル **464 バイト固定** で製品によらない。全体が高エントロピーで、ファイル間・ファイル内に共通ブロック (3 バイト以上の一致) はなく、内部の 16 バイトブロック重複もない。すなわち全体が暗号化され、ファイルごとのランダム性 (または内容依存の鍵・IV) を持つ。

### 3.2 書き手 (観測)

- `LICENCEDIR` の文字列・関連シンボルは `torneplus` にのみ存在し、`AVBase` / `PvrBgApp` には存在しない。書き手は torneplus 内蔵の C++ クラス **`LicenceManager`** (メソッド名群: `GetGaeLicenceData`、`onCacheGaeLicenceData`、`CreateTemporaryTrialLicence`、`checkLicenceFile`、`decryptLicenceData`、`SetEncryptedLicenceData`、`GetLicenceState`、`UpdateLicenceState` 等) と、その ObjC 橋渡し `PvrStoreKitHelper.setToLicenceManager:nonce:` (`0x10041a83c`)。
- パス構築 (`0x100430a48`): Documents 配下に `LICENCEDIR` (ほか `Manage`、`sql3work`、`html`) のパスを保持するオブジェクトが組み立てられる。
- ファイル名の生成 (`0x1003f0e14`、LicenceManager 実装群 `0x1003f0d70`–`0x1003f1844` から呼ばれる): **ファイル名 = `<ライセンス ID>_<SHA-256(ライセンスデータ) の先頭 16 バイトを各バイト mod 26 で 'a'–'z' に写像した 16 文字>.dat`**。接尾辞は乱数ではなく内容のハッシュであり、端末・購入ごとに異なるのはライセンスデータ自体が異なるためである (観測: 同名製品でも端末間で接尾辞が異なることと整合)。

### 3.3 生成フロー (観測 + 一部推論)

入力は 2 経路ある。

1. **GAE ライセンスフロー** (docs/35): 購入・復元のレシート検証 (`opApplePurchases` / `opApplePurchasesCheck`) の応答ライセンス辞書のうち `productid` / `expiredate` / `encrypteddata` が `setToLicenceManager:nonce:` 経由で LicenceManager へ登録され、暗号化されてファイル化される。SE1 で正規版 `SCE_905_PLAY` が購入復元のセッションで出現したことはこの経路と整合する (ただしトライアル→正規へのローカル変換の可能性は静的に排除できない。推論)。
2. **トライアルのローカル生成**: 初回起動時に `CreateTemporaryTrialLicence` がサーバ介在なしに TRIAL ファイルを生成する (観測: 初回起動と同一秒に 3 件が揃う。対象はテーマ 2 件 (001 TorneBlack / 005 Woody) と視聴機能 (905 PLAY))。

### 3.4 形式構造 (観測)

- ファイルはライセンスレコードの集合であり、レコードには **48 バイトの AES-CBC 暗号化コア** がある (`decryptLicenceData` 実体 `0x1003f162c`)。
- 復号鍵は、mobileId (GAE マネージャオブジェクト +0x2c8 の文字列) とレコード内フィールド (オフセット +0x30 の 16 バイト、+0x40 の 32 ビット値、+0x44 の 16 ビット値) とバイナリ埋め込み定数 (47 バイト、`0x1008be779`) から組み立てた 80 バイト入力を KDF ヘルパ (`0x100488724`、出力最大 31 バイト) に通して得る。IV は同埋め込み定数の先頭部を使う。
- 復号後、レコードの 2 フィールド (+0x40 / +0x44) が暗号化側の値と一致するかを検証し、不一致なら出力を消去する (整合性チェック)。
- 鍵導出に mobileId が関与するため、ライセンスファイルは同一インストールインスタンス (同一 mobileId) でのみ読める。ファイル自体に DTCP-IP の証明書・秘密鍵が含まれる形跡はない (レコードの意味は製品 ID・状態・期限等の権利情報であり、消費のされ方 (§3.5) からも権利管理専用と判断する)。

### 3.5 消費者 (観測)

- 読むのは LicenceManager 自身 (起動時・状態問い合わせ時の `checkLicenceFile` / `decryptLicenceData`) で、得られた **ライセンス状態 (所有 / トライアル / 期限) が torneplus 全体の機能ゲート** に使われる。製品 ID 文字列 (`SCE_905_PLAY` 等) の参照は torneplus 内の約 20 関数に分布し、視聴機能 (905)、テーマ (001 / 005)、書き出し (910 EXPORTN)、周辺機器系機能 (900 BDR / 901 WALKMAN / 902 NAVU / 904 HEQ) の可否判定に対応する。
- `AVBase` / `PvrBgApp` は LICENCEDIR を読まない。**LICENCEDIR は DTCP-IP の資格情報供給とは無関係の、アプリ内課金権利の永続化である。** docs/38 で観測された「視聴の権利処理の形跡」はこの権利管理であり、DTCP 資格情報の生成ではなかった。

## 4. DEWEY 側の残件 (調査項目 3)

### 4.1 第 2 供給路 (docs/33 §5.2) の構造

`0x9c500` (仮想 dispatch 経由で到達し、直接の呼出し元はない) を実読した結果、これは **「データ提供オブジェクトの登録」関数** であることが分かった。

- 引数のオブジェクトをセッションオブジェクトの +0x98 に登録 (旧オブジェクトは vtable +0x10 で解放) し、直ちにその vtable +0x78 (データポインタ + 長さの取得) で blob を引き取り、**先頭 16 バイト (定数 `0x358ac0` = 16) を読み飛ばして** 残りを証明書セッタ (`0x8513c`) で DevCert (+0x78) へ設定する。続けて証明書の後処理 (`0x853c8` 等) と鍵ストア (+0x158) への登録 (サイズ定数 `0x358908` = 48) を行う。
- 同一関数後半では、もう 1 つの提供オブジェクト (+0x168) からも同インタフェース (vtable +0x78) で blob を引き取り、パース (`0x85440`) して鍵ストア (+0x158) へ登録する (先頭 4 バイトを除いた部分と、4 バイト値の登録を含む)。すなわち供給路は証明書用と鍵用に **2 つの提供オブジェクト** を持つ。
- 読み飛ばし量 16 バイトは DAL レコードのヘッダ長 (docs/33 §4) と一致し、第 1 供給路 (DAL アイテム #9 のレコード上限 148 バイト = 16 + 132) とも一致する。**2 つの供給路は「16 バイトヘッダ + ペイロード」という同一レコード形式を共有する** (観測)。提供オブジェクトの実体 (torneplus 側の実装か PvrBgApp 内蔵か) は、登録関数自体が仮想 dispatch のため静的に同定できない (§8)。

### 4.2 組立て関数 `0x71814` の呼出し条件

radare2 の全解析 (`aaa`) 後も、`0x71814` への直接呼出し (BL / B) は `PvrBgApp` 内に **存在しない** (呼出し元 0 件)。仮想関数テーブル経由の間接呼出し、または到達不能コードのいずれかであり、「通常再生時に呼ばれるか」は引き続き未確定である。少なくとも直接呼出しで駆動される経路ではない (観測)。

### 4.3 DEWEY の公開面と機能対応

- `PvrBgApp` の export は 4 関数のみ: KeyManager 3 関数 (`PvrDtcpIpKeyManagerInitialize` / `Finalize` / `PvrDtcpIpSetTrustedTimeFunc`) と **`PvrBgAppCreateExportThread` / `PvrBgAppExportCancelFromNotification`** (書き出し機能)。torneplus が import するのは Initialize / SetTrustedTimeFunc / CreateExportThread。
- DEWEY 内には `ISdiSinkAuthMgrListener` / `ISdiSourceAuthMgrListener` の RTTI があり、sink / source 両方の AKE マネージャ実装を持つ。
- したがって DEWEY のアプリ内での表向きの役割は、(a) 初期化時に Documents パスを受け取り資産ファイル経由の資格情報を DAL へ載せる KeyManager、(b) 書き出し (Export) の実行主体、の 2 つが確認できる。LAN 再生の AKE を DEWEY が担うかどうかは、公開面からは読み取れない (§8)。

## 5. torneplus 側の DTCP-IP 鍵管理 (補足の観測)

- torneplus の GAE マネージャオブジェクト (シングルトン配下 +0x8b8) は、mobileId (+0x2c8) と **現在の鍵 ID (keyid、+0x5c0)** を保持する。keyid は GAE ライセンス応答の `key` フィールドから登録される (登録関数 `0x1003564e4` は文字列セッタであり、鍵素材そのものではない)。
- 鍵の世代検証は `opDtcpipKeyCheck` (`0x10042953c`、deviceid と keyid を送信し、応答の `keyUpdate` で再取得を促す) で行われる。呼出しは仮想 / ObjC dispatch 経由で直接呼出し元はない。
- `InAppPurchasesManager::StoreDtcpipKey(String, String, String)`、`DtcpIpUnpackAndStoreParams(const void*, uint)`、`checkDtcpipKey()`、`DtcpIpKeyId(String)`、`DtcpIpKeyManagerInitializer` 等の名前が Xp フレームワークの名前プールに存在する。名前プールはハッシュ引きであり関数ポインタを伴わないため、実装アドレスの同定には至らなかった (§8)。少なくとも、DTCP-IP 鍵に関する「ID の管理」と「パラメータの展開・格納」が torneplus 側にも存在することは名前から分かる。
- torneplus には nasne 側の DTCP クライアント管理 (WebAPI `status/dtcpipClientListGet` / `config/dtcpipClientStop`、`DtcpipClientList` / `StopDtcpIpClient` / `KillDtcpipClientForLive` / `KillDtcpipClientForPlayer`) と、リモート機器向けの `PrepareDtcpIp(PvrDeviceRemote, PvrServiceId)` も存在する。これらは資格情報ではなく制御面である。

## 6. 機能 × 資格情報の対応表 (調査項目 4)

凡例: 〔観測〕= 逆アセンブル / 実物で直接確認、〔推論〕= 構造からの解釈、〔未確定〕= §8 参照。

| 機能 | 必要な資格情報データ | 格納場所 | 生成者 | 発火条件 |
|---|---|---|---|---|
| LAN 再生・ライブ視聴 (AVBase CDtcpIp) | DTCP-IP セッション鍵 (AKE 由来)。証明書・鍵の自前保持なし〔観測〕 | AVBase 内 `CDtcpIpAuth` のバッファ (メッセージ注入)〔観測〕 | AKE の ECC は DEWEY のみ実装〔観測〕。制御経路は〔未確定〕 | 再生開始 (`ActivateDtcpIp` 等)〔観測〕 |
| 書き出し (Export) | DTLA デバイス証明書 + 秘密鍵 (DEWEY の DAL #9 / #13)〔推論〕 | PvrBgApp の DAL (メモリ内素材オブジェクト)〔観測〕 | 資産ファイル経由の投入、または第 2 供給路〔未確定〕 | `PvrBgAppCreateExportThread`〔観測〕 |
| DEWEY DAL への素材投入 (第 1 供給路) | 資産レコード (16 バイトヘッダ + ペイロード、最大 2,120 バイト)〔観測〕 | `Documents/PvrAssetData.cxml` → 資産ローダ → DAL アイテム 1〔観測〕 | torneplus の GAE ライセンスフロー (2 層復号 → TLV タグ `PRMA`) が生成・保存〔観測〕 (docs/35) | 購入・復元時のライセンス取得。**投入の成立自体は未再現**〔観測〕 (docs/34 §10) |
| DEWEY への第 2 供給路 | 同形式レコード (証明書用と鍵用の 2 系統)〔観測〕 | 提供オブジェクト (vtable +0x78 で取得)〔観測〕 | 提供オブジェクトの実体は〔未確定〕 | 登録関数 `0x9c500` の実行時 (条件〔未確定〕) |
| 視聴権・機能ゲート (視聴、テーマ、書き出し可否等) | ライセンスレコード (製品 ID・状態・期限)〔観測〕 | `Documents/LICENCEDIR/*.dat` (464 バイト、暗号化)〔観測〕 | torneplus の LicenceManager (GAE 由来 + トライアル自動生成)〔観測〕 | 初回起動 (トライアル)、購入・復元 (GAE)〔観測〕 |
| DTCP-IP 鍵の世代管理 | keyid (文字列) と mobileId〔観測〕 | torneplus の GAE マネージャオブジェクト (メモリ内)〔観測〕 | GAE ライセンス応答の `key` フィールド〔観測〕 | ライセンス取得時。検証は `opDtcpipKeyCheck`〔観測〕 |
| 外出先視聴 (Telepathy) | TpStorage 等のデバイス永続データ〔観測〕 | `Library/Application Support/TP/device/`〔観測〕 | Telepathy スタック〔観測〕 (docs/38 §3.4) | 初回起動・ペアリング〔観測〕 |
| 資産ファイルの暗号鍵 G | mobileId 先頭 48 バイト + キーチェーン UUID 16 バイトの SHA-256〔観測〕 (docs/36) | torneplus / PvrBgApp の大域変数 (メモリ内)〔観測〕 | mobileId は GAE (`opGetMobileId`)、UUID は初回利用時に生成してキーチェーン登録〔観測〕 | 初回起動〜ライセンス取得時 |

キーチェーン項目の向きについての確定 (docs/36 §5 / docs/38 §3.2 の懸案): 実機での登録実物 (docs/38) が正であり、**service = `torne moible`、account = `com.playstation.tornemobile.storage`** である。docs/36 §5 の静的割当ては逆だったため、本段で訂正した。

## 7. cxml / DEWEY の位置づけ (確定度)

- **確定したこと**: (a) LAN 再生は cxml なしで成立する (docs/38 の実機観測 + 本書 §2 の構造)。(b) AKE 暗号の実装は DEWEY のみ。(c) LICENCEDIR は DTCP と無関係の権利管理。(d) cxml は「DEWEY の DAL を満たすため」にライセンス取得段階で生成されうるファイルであり、その投入成立は未再現のまま。
- **有力な解釈 (推論)**: DEWEY / DAL 資格情報の主たる消費者は書き出し機能 (有料ライセンス SCE_910_EXPORTN と対応し、`PvrBgAppCreateExportThread` が唯一の実行入口として export されている) であり、LAN 再生は AVBase 側の別経路 (セッション鍵のみを必要とし、Auth バッファへ注入される) で回っている。
- **残る不確定性**: LAN 再生時に DEWEY の AKE が実際に駆動されるか、その際 DAL 資格情報を使うかは、静的解析の公開面からは決着しない。docs/34 の「素材の出所は確定」という冒頭表現はこの不確定性を覆っていたため、本段であわせて訂正した。

## 8. 未確定事項

1. LAN 再生時の AKE の駆動経路 (torneplus プレイヤ層 → DEWEY の仲介の有無、セッション鍵が AVBase の Auth バッファへ届く具体的経路)。
2. 第 2 供給路の提供オブジェクト (+0x98 / +0x168) の実体と、登録関数 `0x9c500` の実行条件。
3. 組立て関数 `0x71814` の間接呼出しの有無と実行条件 (直接呼出しは存在しないことを確認)。
4. DAL アイテム 1 への投入の成立条件 (docs/34 §10 から継続。合成データでは転送層がエラーを返した)。
5. `InAppPurchasesManager::StoreDtcpipKey` / `DtcpIpUnpackAndStoreParams` の実装と呼出し元 (名前プールがハッシュ引きのため未同定)。
6. SE1 で正規版 `SCE_905_PLAY` ファイルが GAE 経由かローカル変換か (タイミングは GAE 経由と整合するが確定しない)。
7. Android 版での対応関係 (本書 §2.2 の定数所在は確認したが、LICENCEDIR 相当の権利管理や第 2 供給路の有無は Android 側では未調査)。

## 9. 既存文書への訂正 (本段で反映)

- docs/34: 冒頭の状態行を、実証範囲 (GET 経路の逐語コピー確定、資産経路はアイテム 1 処理の入口まで、投入成立は未確定) に合わせて書き換え、本書への参照を追加。
- docs/36 §5: キーチェーン項目の service / account の割当てを実機の登録実物 (docs/38 §3.2) に合わせて訂正。§7: 「視聴ライセンス取得まで至っていない端末では資産ファイル自体が生成されない」との解釈に、LICENCEDIR による権利処理 (本書 §3) と GAE→cxml フローは別系統である旨の注記を追加。
- docs/38 §3.5: 視聴が cxml なしで成立した事実について、本書 (AVBase の資格情報源、LICENCEDIR の位置づけ) と docs/21 §8 / docs/33 §12 への相互参照を追加。§4 の「docs/36 の service / account 割り当ての訂正要否」は本書 §6 で決着した旨を注記。

## 10. 作業素材

- 作業領域: `SonyNasne-DTCP.work/2026-11-16-torne-reinvest/` (走査スクリプトと出力)。
- 使用した走査: 曲線定数の 6 表現走査、CDtcpIp コード群のデータ参照走査、LICENCEDIR 実ファイルの構造比較 (サイズ・共通ブロック・内部重複)。
