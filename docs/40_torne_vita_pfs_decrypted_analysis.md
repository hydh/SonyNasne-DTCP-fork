# 40. torne PlayStation®Vita 版 (PCSC00025) の PFS 復号済みコピー解析 — リソース平文化と残る SELF 暗号化

[39](39_torne_vita_static_analysis.md) の続き。あちらで対象とした raw コピー (PFS 暗号化のまま) に対し、本人が PFS 層を通したコピーを marnux `~/ダウンロード/torneMobileBackup/Vita_App/` に用意したので、その内容を確認し、平文で読める範囲を本解析した記録 (2026-11-16 実施)。対象は marnux 上のファイルのみで、実機 (nasne / Vita 本体) には触っていない。資格情報については入手経路の調査のみで、鍵素材そのものの抽出・復号・導出は行っていない。

**現在の到達点**: 本コピーは **PFS 層は復号されているが、実行ファイルの SELF 層は暗号化されたまま**である。リソース類 (Pvr*.cxml、channelList.bin、param.sfo、LiveArea 定義) は全て平文で読めるようになり、UI 文字列から Vita 版の機能構成と、DTCP-IP アクティベーションや SEN アカウント登録といった資格情報まわりの**経路の手がかり**が得られた。一方 eboot.bin / eboot2.bin は SELF コンテナのままでセグメントが暗号化されており (全域エントロピー 8.00)、strings / シンボル解析は依然として不可能である。したがって [21](21_torne_mobile_ipa_static_analysis.md) の nasne WebAPI 62 エンドポイントとの **API 単位の突き合わせは本コピーでも未了**であり、実施には SELF 復号済み (ELF 化された) eboot の調達が前提になる。また本コピーは**ベースアプリ v1.00 のみ**で、パッチ v2.02 を含まない (実効バージョン 2.02 の姿は未解析)。

## 1. 対象と同定

- 配置: marnux `~/ダウンロード/torneMobileBackup/Vita_App/`。構成はアプリ本体のファイル一式のみで、[39](39_torne_vita_static_analysis.md) §1.1 のベースアプリ (`ux0/app/PCSC00025/`) に対応する。パッチ (`ux0/patch/PCSC00025/`) 側のファイル (実効 2.02 の eboot、`TelepathyDeviceConfig.bin`、`initialContent.db`、`NicoJkResource.cxml` 等) は含まれない。
- バージョン (param.sfo の実読、事実): TITLE = torne™ PlayStation®Vita、TITLE_ID = PCSC00025、APP_VER = **01.00**、VERSION = 01.00、CATEGORY = `gdc`、CONTENT_ID = `JA0003-PCSC00025_00-TORNEVITA0000000`、PSP2_DISP_VER = 02.020、PUBTOOLINFO = `c_date=20121207,has_bg=1,sdk_ver=02000000`。[39](39_torne_vita_static_analysis.md) のベースアプリ側の記録と一致する。`version.txt` の内容は `Ver.1.00.2012120513`。
- 主要ファイル (サイズは [39](39_torne_vita_static_analysis.md) の raw コピーと一致するが、PFS 層が剥がれたため SHA-256 は全て異なる):

| ファイル | サイズ | SHA-256 | 状態 |
|---|---|---|---|
| eboot.bin (v1.00) | 4,109,536 | `dbca41cf9289fab4d891d9519a9231a61e115188433d0308af10ae50abb32a7c` | SELF 暗号化 (§2) |
| eboot2.bin | 135,536 | `2eee867fd01c2a2571d76b34ee2ea7de2f14c64ec9c3210e11dfa66fa3ae991d` | SELF 暗号化 (§2)。役割は未同定のまま |
| PvrResource.cxml | 2,432,304 | (未採取) | 平文 (マジック `SPVR`) |
| PvrTheme.cxml | 3,866,528 | (未採取) | 平文 |
| PvrVersionHistory.cxml | 11,648 | (未採取) | 平文 |
| PvrBgAppResource.txt | 660 | (未採取) | 平文 (書き出し通知文) |
| channelList.bin | 15,347 | (未採取) | 平文構造 (`CHLISTID` / `SVRCONFG` レコード) |
| sce_sys/param.sfo | — | `c39a1caf2baf83db59f4c62655413ee866dff13762a9f74df568a722bfc5d119` | 平文 (`\0PSF`) |
| sce_sys/livearea/contents/template.xml | — | (未採取) | 平文 (§3.3) |

- `sce_module/` の `libc.suprx` / `libfios2.suprx` / `libult.suprx` と `sce_sys/about/right.suprx` はいずれも `SCE\0` で始まる SELF 形式 (システムランタイムでありアプリ固有ロジックではない)。
- `savedata/` 配下はアイコン画像のみ (セーブデータ実体ではない)。

## 2. 復号状態の判定 — 2 層のうち PFS 層のみ復号

Vita のアプリファイルには (a) ストレージ上の PFS 暗号化と (b) 実行ファイル自体の SELF 暗号化の 2 層がある。本コピーの状態は次のとおり (いずれも実測の事実)。

### 2.1 PFS 層: 復号済み

- [39](39_torne_vita_static_analysis.md) では高エントロピーで読めなかったファイルが全て本来の形式で読める: `PvrResource.cxml` は `SPVR` マジック + 可読な文字列テーブル、`channelList.bin` は `CHLISTID` / `SVRCONFG` のレコード構造、`param.sfo` は `\0PSF` マジック、`version.txt` と LiveArea `template.xml` は平文テキスト、マニュアル PNG も本来のマジックを持つ。
- ファイルサイズが [39](39_torne_vita_static_analysis.md) の raw コピーと一致し SHA-256 のみ異なる点も、PFS 層だけが剥がれたことと整合する。

### 2.2 SELF 層: 暗号化のまま (eboot は依然として読めない)

- eboot.bin / eboot2.bin とも先頭は SELF ヘッダ (`SCE\0`) で、内包 ELF ヘッダはオフセット 0xa0 に平文で存在する (SELF の通常構造)。しかし**セグメント本体は全域でエントロピー 8.00** (64 KiB 窓でファイル全域を走査、最小 7.96) であり、暗号化されている。
- 文字列の実測: ASCII 文字列 (最小長 4) は 50,790 件抽出されるが、これは暗号文中の偶然の可読断片であり、**長さ 12 以上の文字列は 23 件のみで、内容 ID (`JA0003-PCSC00025_00-TORNEVITA0000000`、平文ヘッダ領域由来) を除き全て無意味な断片**である。`Sce*` / `sce*` のライブラリ名・モジュール名は 0 件。iOS 版で 66,894 行の意味ある文字列が取れた ([21](21_torne_mobile_ipa_static_analysis.md) §1.2) のとは対照的である。
- すなわち本コピーは「本体の PFS 復号済みマウントからのコピー」相当であり、SELF 復号 (デバイス上での ELF 化ダンプ等) は行われていない。**eboot のコード・文字列・シンボル解析は本コピーでも実施不能**であり、§4・§6 の未確定事項はこの制約による。

## 3. 平文リソースから分かる機能と通信の輪郭

eboot は読めないが、`PvrResource.cxml` の文字列テーブル (ASCII 30,026 件 + 日本語 UI 文約 1,700 件を抽出) と UI 文字列 ID の census から、v1.00 時点の機能構成が具体的に分かる。以下はリソースに実在する文字列 ID / 文 (事実) と、その解釈の区別を明記する。

### 3.1 nasne 連携機能 (UI 証拠)

次の設定・操作ダイアログの文字列 ID が存在する (抜粋):

- 機器管理: `dialog_setting_nasne_list`、`dialog_setting_nasne_apply`、`dialog_setting_nasne_unregist_1` / `_progress`、`dialog_settings_nasne`、`dialog_settings_nasne_initialize`、`dialog_setting_nasne_initialize_contents_1/2`、`dialog_setting_nasne_channel_scan_end`。nasne の登録・一覧・登録解除・初期化・チャンネルスキャン結果確認をアプリから行う機能がある。
- ストレージ登録: `dialog_setting_nasne_storage_regist_1/2`、`dialog_setting_nasne_storage_regist_progress`、`dialog_setting_nasne_storage_unregist_1/2/3`、`dialog_setting_regist_nasne_storage`。nasne 側ストレージ (録画先) の登録・解除フローが独立に存在する (iOS 版 WebAPI の `config/HDDRegister` 系に対応する機能とみられる — 解釈)。
- チャンネル/番組表/予約: `dialog_reservation`、`dialog_custom_reservation`、`dialog_search_keyword_detail`、`dialog_setting_channel_scan` 等、予約・番組表・検索の UI 一式 (PVR プラットフォーム共通の UI 資源を含む)。
- その他プラットフォーム系: BD レコーダー登録 (`dialog_setting_bd_recorder_*`)、PSP / ストレージへのコピー (`dialog_copy_to_psp`、`dialog_copy_to_storage`) は、PVR プラットフォームが PS3 torne 等と共有する資源の名残りを含むとみられる (解釈。Vita 版で有効な機能かはリソースだけでは決まらない)。

### 3.2 ビデオ書き出し「ウケトルネ」 (Vita 固有機能)

- `PvrBgAppResource.txt` (平文) と `PvrResource.cxml` に、メモリーカードへのビデオ書き出しの通知・設定文が一式ある: `msg_psv_notification_export_*`、`dialog_setting_quick_export_1`–`6`、`dialog_setting_empr_*` (保存場所の作成・削除・サイズ選択)、`helpline_psv_mc_create_video_export_space` 等。機能名は利用規約文中の **uke-torne (ウケトルネ)**。
- 日本語文からの仕様 (事実として文面を記録): 「書き出したビデオは、ビデオの保存場所を作成した PS Vita でのみ再生できます」「1 台の PS Vita の『ウケトルネ』で使用できるメモリーカードは 4 枚まで」「PS Vita の初期化を行うと、その PS Vita で書き出したすべてのビデオが再生できなくなります」「ビデオの保存場所を削除すると、書き出したすべてのビデオも削除されます」。[39](39_torne_vita_static_analysis.md) §5 の umass FAT32 コンテナ (`TORNE/recording` / `TORNE/unpromoted`) がこの書き出し先である。
- 解釈: 書き出しは機器束縛付きの保護コピーであり、DTCP の管理下にあるコピー/ムーブ系機能と整合する。iOS 版の解析 ([21](21_torne_mobile_ipa_static_analysis.md)) の範囲では対応する「端末への書き出し」機能の痕跡は無く、これは Vita 版固有の機能である。

### 3.3 外部サービス・ドメイン (リソース内の平文)

- ドメインの出現は次の 4 件のみ (事実): `legaldoc.dl.playstation.net` (PSN 利用規約)、`torne.scej-online.jp`、`twitter.com` (Twitter 連携)、`www.scei.co.jp` (プライバシーポリシー)。
- LiveArea `template.xml` (本コピーで平文化) のリンクは [39](39_torne_vita_static_analysis.md) §4.2 と同一: `http://torne.jp/`、`http://torne.scej-online.jp/`、`http://www.jp.playstation.com/ps3/torne/tornev/`、`https://tv.so-net.ne.jp/chan-toru/` (So-net のリモート予約「チャン・トル」)。
- チャン・トル連携はアプリ内にも設定として存在する (事実): `dialog_setting_chantoru_description_1/2`、`dialog_setting_chantoru_notice_1/2`、`dialog_setting_chantoru_register_nasne`。
- **陰性 (リソースの範囲)**: iOS 版の資格情報経路で中核だった GAE バックエンド ([35](35_torne_asset_origin.md)) を示すドメイン (appspot / googleapis 系) はリソース内に無い。Telepathy レゾルバ (`tp-resolver.ndmdhs.com`、iOS 版はバイナリ文字列) もリソース内には無い。ただし eboot が読めないため、バイナリ側の陰性としては主張できない。

### 3.4 リソース内に無いもの (陰性の範囲明記)

平文ファイル全て (cxml 3 件、txt、channelList.bin、template.xml) を走査した範囲では、**API パスらしき文字列 (config/・recorded/・schedule/・status/ 配下の名前を含む) は 0 件、ポート番号 (60151 / 64210 / 58890) の文字列も 0 件**だった (事実)。エンドポイントやポートは iOS 版でもバイナリ側にあったもので、リソースに無いこと自体は不自然ではないが、本コピーではこれらを裏付ける材料が得られなかったという位置づけである。

## 4. nasne との通信方法 — iOS 版との比較の現在地

| 項目 | iOS 版 ([21](21_torne_mobile_ipa_static_analysis.md)) | Vita 版 (本コピー) |
|---|---|---|
| WebAPI エンドポイント 62 件 | torneplus の文字列から全数抽出済み | **判定不能** (eboot の SELF 暗号化)。UI 上は登録・ストレージ登録・チャンネルスキャン・予約等、WebAPI 駆動とみられる機能が揃う (§3.1) |
| UPnP / SOAP テンプレート (ContentDirectory / X_PvrControl / X_ScheduledRecording) | バイナリ内に埋め込みを確認 | 判定不能 (同上)。リソースにも痕跡なし (§3.4) |
| DMS 転送ポート 60151 / ObjID 形式 URL | テンプレート文字列を確認 | 判定不能 (同上) |
| 発見 (SSDP) | 実装文字列あり | 判定不能 (同上) |
| リモート視聴 | Telepathy (レゾルバ・URN・永続ストレージ) | Telepathy 永続ストレージが同型に存在 ([39](39_torne_vita_static_analysis.md) §3)。UI 文では「リモートプレイ」呼称で、**インターネット経由のリモートプレイではテレビ視聴・ビデオ再生はできない**旨の制限文が v1.00 のリソースにある (事実)。レゾルバ等の通信詳細は判定不能 |
| ローカル書き出し | 解析範囲で痕跡なし | **ウケトルネ** (機器束縛付き書き出し、umass コンテナ) が固有機能として存在 (§3.2) |
| nasne HOME | `nasne_home/index_mobile.html` の URL テンプレート | 「インターネットブラウザーで nasne HOME を開く」旨の UI 文あり (事実)。アプリ内 WebAPI とは別の、ブラウザ連携 |

要するに、**機能面では iOS 版と同系の PVR プラットフォームであることが UI 資源から強く裏付けられたが、プロトコル面 (API・UPnP・ポート) の同一/相違は eboot の制約により引き続き未確定**である。自作クライアントの基礎資料としては、Vita 版の機能棚卸し (特にストレージ登録と書き出し) が新たに得られた一方、API 仕様そのものは iOS 版解析 ([21](21_torne_mobile_ipa_static_analysis.md)) が引き続き一次資料になる。

## 5. 資格情報 (DTCP-IP) の入手経路 — iOS 版との比較

### 5.1 既存確定事項 ([39](39_torne_vita_static_analysis.md) §6 の要約)

- iOS 版: アプリ単位の供給。GAE + App Store レシート → 暗号化資産 `PvrAssetData.cxml` → DAL #9 (証明書) / #13。
- Vita 版: `PvrAssetData.cxml` は存在せず、代わりにシステム領域 `ur0:/dtcp/param_tbl.enc` (368 バイト、OpenSSL Salted 形式) がサンドボックス外に 1 件存在する (中身の復号は範囲外として未実施)。

### 5.2 本コピーで新たに得られた経路の手がかり (UI 証拠)

- **DTCP-IP アクティベーションの存在**: 文字列 ID `msg_psv_dtcpip_activate_start` / `_processing` / `_success` / `_error` と、設定ダイアログ `dialog_setting_dtcp_ip_1` が存在する (事実)。日本語文には「インターネット経由でのアクティベーション (認証) が必要です。」という文がある (事実。どの ID に対応するかは cxml の対応付け未解析のため、この文が DTCP-IP アクティベーション専用かは断定しない)。
- **ネットワーク機能の SEN サインイン前提**: 利用規約文「(1) 本サービスは、SEN/PSN にサインインしている場合にのみ機能します」、エラー文系 `msg_psv_error_no_signin` / `msg_psv_firstsettings_error_no_signin` が存在する (事実)。
- **リモート視聴のアカウント登録は SEN アカウント束縛**: `dialog_setting_remote_account_regist` と文「現在サインインしている SEN アカウントで登録が行われます」「ログインには登録した SEN アカウントのサインイン ID (メールアドレス) を使います」(事実)。
- リソース内に GAE 系ドメインが無いことは §3.3 のとおり。

### 5.3 解釈

Vita 版の資格情報まわりは、iOS 版の「アプリがサーバから暗号化資産を受け取り、アプリ内で復号して DAL に投入する」形とは異なり、**(a) DTCP パラメータはプラットフォーム側が `ur0:/dtcp/` に保持し、(b) 利用開始にはインターネット経由のアクティベーション手続きがあり、(c) ネットワーク機能とリモート視聴の登録は SEN/PSN アカウントに束縛される**、という三層の形を UI 証拠と配置が示している (解釈)。アクティベーションの通信先・プロトコル、AKE の実行主体 (システムの DTCP スタックか eboot 内蔵実装か)、`param_tbl.enc` の生成・更新がアクティベーションとどう結びつくかは、eboot が読めないため未確定のままである。

## 6. 未確定事項

- **SELF 復号済み eboot の調達が全ての前提**: ベース v1.00 とパッチ v2.02 の双方について、SELF 復号され ELF として読める eboot が得られれば、[21](21_torne_mobile_ipa_static_analysis.md) の 62 エンドポイントとの API 単位の突き合わせ、UPnP テンプレート・ポート・User-Agent・SSDP の確認、DTCP スタックの所在 (アプリ内蔵かシステムか)、`param_tbl` 参照の有無、アクティベーションの通信先の同定が可能になる。本コピー (PFS 復号のみ) では到達できない。
- 本コピーは v1.00 のみであり、実効 2.02 の機能差 (パッチ側にのみある `TelepathyDeviceConfig.bin`、`initialContent.db` 等) は未解析。
- cxml 内の文字列 ID と日本語文の対応付け (フォーマット解析) は未実施。「インターネット経由でのアクティベーション」文の帰属 ID は未同定。
- `eboot2.bin` の役割は本コピーでも未同定 (SELF 暗号化のため)。
- umass コンテナへ実際に書き出した際のファイル命名・形式は、書き出し実績のあるデータの採取が前提 ([39](39_torne_vita_static_analysis.md) §7 と同じ残件)。
