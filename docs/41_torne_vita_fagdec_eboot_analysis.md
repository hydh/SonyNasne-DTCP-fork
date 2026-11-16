# 41. torne PlayStation®Vita 版 (PCSC00025) の FAGDec 復号済み eboot 解析 — WebAPI 定義テーブル全読とシステム DTCP スタックの確定

[39](39_torne_vita_static_analysis.md)・[40](40_torne_vita_pfs_decrypted_analysis.md) の続き。あちらでは eboot.bin の SELF 層が暗号化されたままで strings / シンボル解析ができず、nasne WebAPI のエンドポイント単位の突き合わせが未了だった。本人が FAGDec で SELF 復号した ELF を marnux `~/ダウンロード/torneMobileBackup/Vita_App02/` に用意したので、それを本解析した記録 (2026-11-16 実施)。対象は marnux 上のファイルのみで、実機 (nasne / Vita 本体) には触っていない。資格情報については入手経路の調査のみで、鍵素材そのものの抽出・復号・導出は行っていない (`ur0/dtcp/` はハッシュ比較のみ)。

**現在の到達点**:

1. **Vita 版も iOS 版と同じ nasne WebAPI を使うことが確定した。** eboot 内に WebAPI の**定義テーブル** (JSON キー名とエンドポイントパスの対) がデータとして存在し、全読できた。iOS 版の 62 件 ([21](21_torne_mobile_ipa_static_analysis.md) §3.2) との突き合わせは、**両版共通 52 件 / Vita 2.02 のみ 4 件 / iOS のみ 6 件**。さらにベース v1.00 のテーブルは **109 件**あり、iOS の 62 件の外側に NAS 設定・DMP 登録・メール・掲示板・FW 更新など当時の nasne WebAPI の全面に及ぶ定義を含む (Vita 独自 57 件)。v2.02 ではこのテーブルが torne の実用範囲に刈り込まれている。
2. **DTCP-IP スタックはアプリ内蔵ではなく Vita のシステムライブラリ `SceDtcpIp` であることが確定した。** eboot / eboot2 とも `libSceDtcpIp` を import し、iOS 版にあった DEWEY バナー・Sdi* AKE クラス・dtcp.com ヘッダ・DLNA プロファイル名はアプリバイナリ内に存在しない。アプリ側はラッパ層 (LoadDtcpIpUtility / ActivateDtcpIp 等) のみを持ち、`param_tbl` や `ur0` のパス文字列もアプリ内に無い — パラメータテーブルへのアクセスはシステム側で完結する。[39](39_torne_vita_static_analysis.md) §6.3 の「プラットフォーム側が保持する形」という解釈が、バイナリ側から裏付けられた。
3. 認証ヘッダ名 **`X-DTVToken` が Vita 版の全 ELF に平文で存在する** (iOS 版は 3 バイナリとも不在だった、[21](21_torne_mobile_ipa_static_analysis.md) §3.2 の実測陰性と対照的)。
4. `ur0/dtcp/param_tbl.enc` は、本人が録画終了・再生まで回した後のコピーでも **SHA-256 が [39](39_torne_vita_static_analysis.md) の測定値と完全一致** し、内容が変わっていない。
5. `eboot2.bin` の役割が確定した: バックグラウンド側の torne プロセス (`BgTorne` / `PvrBgApp_Vita`) で、iOS 版の PvrBgApp に相当する。WebAPI は 11 件 (v1.00) / 13 件 (v2.02) のサブセットを使う。

## 1. 対象と同定

### 1.1 Vita_App02 の構成

marnux `~/ダウンロード/torneMobileBackup/Vita_App02/` の内容 (事実):

- `ux0/FAGDec/app/PCSC00025/` と `ux0/FAGDec/patch/PCSC00025/`: FAGDec の出力一式 (復号済み ELF、`.sha256`、`.temp`、`self_auth.bin` 144 バイト、`sce_module/` のシステムランタイム ELF)。
- `ur0/dtcp/param_tbl.enc` (368 バイト)。
- `ux0/user/00/savedata/PCSC00025/`: セーブデータの raw コピー (PFS 暗号化のまま、§6.3)。

含まれていないもの: `ux0/app`・`ux0/patch` の PFS コピー自体と、**umass コンテナ**。したがって [39](39_torne_vita_static_analysis.md) §5・§7 の残件だった「umass へ実際に書き出した際のファイル命名・形式」は本コピーでも観測できない。

なお `Vita_App01/` は [40](40_torne_vita_pfs_decrypted_analysis.md) で解析した `Vita_App/` を改名したものである (param.sfo の APP_VER = 01.00 を再確認した)。

### 1.2 ELF の確認 — 形式と完全性

FAGDec 出力の 4 ELF はいずれも正規の Vita 実行形式で、FAGDec が添付した `.sha256` (バイナリ 32 バイト) と実ファイルの SHA-256 が全て一致した (事実):

| ファイル | サイズ | SHA-256 | ELF 種別 | strings 件数 (最小長 4) |
|---|---|---|---|---|
| app/eboot.bin.elf (v1.00) | 8,349,339 | `7efa65c45e3aef6904c7c54d2cb73bb59354bce489196038152fe8f919b54d61` | ET_SCE_EXEC (0xfe00) | 43,852 |
| patch/eboot.bin.elf (v2.02) | 12,352,940 | `0627396d84ee721cc0ba46bb8a7c5e42295e83527c8fbea7036439c22adaae50` | ET_SCE_RELEXEC (0xfe04) | 53,898 |
| app/eboot2.bin.elf | 264,123 | `33a04dd286ac135a7f70aaaea7688f49cc739d1202596ad0e7f8705a3cf293b9` | (同形式) | 1,856 |
| patch/eboot2.bin.elf | 318,032 | `0002b8fa60eae0cf6f29aed0d9c860eebaed55d0cc7ce15fe8e663824a718f99` | (同形式) | 2,054 |

- 形式: ELF32 リトルエンディアン ARM (EABI5)、プログラムヘッダ 3 件、セクションヘッダなし — FAGDec 出力の通常形。シンボルテーブルは無いが、文字列・C++ クラス名 (RTTI)・SQL 文・import ライブラリ名 (`libSce*_stub`) が平文で読める。[40](40_torne_vita_pfs_decrypted_analysis.md) §2.2 で「長さ 12 以上の意味ある文字列は皆無」だった SELF 暗号化状態とは対照的に、全面可読である。
- バージョン帰属: `app/` = ベース v1.00、`patch/` = パッチ v2.02。[39](39_torne_vita_static_analysis.md) §1.1 の param.sfo 実読 (ベース APP_VER 01.00 / パッチ 02.02) と配置 (ux0/app と ux0/patch への FAGDec 適用) に基づく。内容面でも、v1.00 側にだけ `libSceNpCommerce2` import と大規模な WebAPI テーブルがあり、v2.02 側にニコニコ実況 (NicoJk) の OAuth 文字列と TelepathyDeviceSDK-1.3.5.1 (2014-08-26 ビルド) のパスがあることと整合する。
- `sce_module/` の ELF (libc / libfios2 / libult) も復号されているが、システムランタイムであり本解析の対象外とした (サイズのみ記録: app 側 libc 408,840 / libfios2 245,176 / libult 140,504 バイト)。
- 抽出した strings は作業領域 `SonyNasne-DTCP.work/2026-11-16-vita-fagdec/` に保存した (リポジトリ外)。

## 2. eboot2.bin の役割 — バックグラウンド torne (BgTorne)

両版の eboot2 に `BgTorne`、`PvrBackgroundMain`、`PvrBgApp_Vita`、`app0:PvrBgAppResource.txt` の文字列があり、import には `libSceDtcpIp`、`libSceAppUtilUmass`、`libSceNotificationBgApp` (v1.00) 等が並ぶ (事実)。すなわち **eboot2 はバックグラウンドで動く torne プロセス** で、iOS 版の PvrBgApp (バックグラウンド側フレームワーク) に相当するモジュールである。[39](39_torne_vita_static_analysis.md)・[40](40_torne_vita_pfs_decrypted_analysis.md) で未同定だった eboot2 の役割はこれで確定した。

eboot2 が使う WebAPI は本体のサブセットである (パス文字列の実在、事実):

- v1.00 (11 件): `config/PINVerify`、`config/dtcpipClientStop`、`config/finishSetup`、`recorded/PMTMapGet`、`recorded/SEMapDataGet`、`recorded/recordedContentAdditionalInfoGet`、`recorded/recordedContentThumbnailGet`、`recorded/thumbnailMapGet`、`recorded/titleListGet`、`status/dtcpipClientListGet`、`status/isFinishSetup`。
- v2.02 (13 件): 上記に `recorded/recordedContentChpDataGet` と `status/networkIfInfoGet` が加わる。

録画メタデータ・サムネイル・DTCP-IP クライアント状態といった、バックグラウンド処理 (書き出しやダウンロード系) に必要な範囲に限られている (解釈)。

## 3. nasne WebAPI — 定義テーブルの全読と iOS 版との突き合わせ

### 3.1 定義テーブルの構造

両版の eboot には、文字列テーブル上に連続した **WebAPI 定義テーブル** がある (事実)。エンドポイントパス (`config/currDateSet` 等) と、そのリクエスト/レスポンスの JSON キー名 (`currDate`、`type`、`parentalRatingInfo` 等) が交互に並ぶデータ駆動の定義で、PVR プラットフォームの WebAPI 層がこの表からリクエストを組み立てる構造と読める。

- v1.00: テーブルは strings の連続領域に **109 件** のパスを含む。
- v2.02: 同領域に **56 件**。これに加えて `config/remoteRegister` がテーブル外 (チャンネルリストの SVRCONFG レコード定義に隣接する文脈) に 1 件残る。

### 3.2 iOS 版 62 件との分類

[21](21_torne_mobile_ipa_static_analysis.md) §3.2 の 62 件を、Vita 側のフルパス文字列の実在で分類した (事実)。「実在」は eboot 内に `カテゴリ/名前` の文字列があることを指し、定義の存在であって実行時に必ず使われることまでは意味しない。

**両版共通 (52 件)**:

- config/ (16): HDDRegister、HDDRegisterProgressGet、HDDRelease、PINVerify、areaInfoSet、boxNameSet、channelScanCancel、channelScanProgressGet、channelScanStart、currDateSet、dtcpipClientStop、finishSetup、internalHDDInitialize、internalHDDInitializeProgressGet、parentalRatingInfoSet、recNgListDelete
- recorded/ (10): PMTMapGet、SEMapDataGet、recordedContentAdditionalInfoGet、recordedContentAdditionalInfoSet、recordedContentResumePositionSet、recordedContentThumbnailGet、thumbnailMapGet、titleDelete、titleListGet、titleUpdate
- schedule/ (6): conflictListGet、reservedInfoBitrateGet、reservedInfoCreate、reservedInfoDelete、reservedInfoUpdate、reservedListGet
- status/ (20): BCASInfoGet、CAMsgInfoGet、EMMMsgInfoGet、EPGVersionInfoGet、HDDInfoGet、HDDListGet、areaInfoGet、boxNameGet、channelListGet、currDateGet、dmsStreamStopReasonListGet、dtcpipClientListGet、isFinishSetup、liveStreamPCRGet、liveStreamStatusListGet、networkIfInfoGet、parentalRatingInfoGet、recNgListGet、softwareVersionGet、updateCheck

**Vita 2.02 のみ (v1.00 には無い、4 件)**: `config/mobileBitrateInfoSet`、`recorded/recordedContentChpDataGet`、`status/liveStreamPCRGet2`、`status/mobileBitrateInfoGet`。モバイルビットレート設定とチャプタデータ・PCR 取得の第 2 版で、いずれも iOS 版にも存在する (後発機能が 2017 年のパッチで Vita にも入った形)。

**iOS のみ (Vita 両版に文字列が無い、6 件)**: `recorded/recordedContentCountGet`、`recorded/recordedContentMaxCountGet`、`schedule/reservedListGet2`、`status/dtvtunerDeviceInfoGet`、`status/multiTunerLiveStreamStatusListGet`、`status/requestClientInfoGet`。裸名での部分一致でも両版とも 0 件であり、近似名 (別名) も見つからなかった。件数取得や複合チューナ状態など、Vita 版が代替手段 (titleListGet の応答内情報等) で済ませている可能性があるが、文字列解析の範囲では未確定である。

**Vita 独自 (iOS の 62 件に無いもの)**: 次節のとおり v1.00 のテーブルに 57 件あり、v2.02 ではほぼ全てが消える。

### 3.3 v1.00 テーブルの Vita 独自 57 件 — 当時の nasne WebAPI 全面

v1.00 の定義テーブルには、iOS の 62 件の外側に次の 57 件がある (事実、全てパス文字列の実在):

- config/ (24): DMPAutoRegisterInfoSet、DMPRegister、DMPRelease、HDDPowerSavingModeSet、LEDControl、NASEnableSet、NASNameSet、NASSharedNameSet、NASWorkgroupSet、additionalInfoSet、bsPowerSupplySet、downloadingPermissionSet、eventRelayInfoSet、initialize、initializeProgressGet、mailDelete、mailReadFlagSet、networkIfInfoSet、parentalRatingPasswordSet、remoteRegister、remoteRelease、updateFileDownload、updateFileUpload、updateProgressGet
- recorded/ (3): ResolutionMapGet、SEMapBodyGet、SEMapHeaderGet
- status/ (30): DMPAutoRegisterInfoGet、DMPInfoGet、DMPListGet、HDDPowerSavingModeGet、NASInfoGet、TOTStatusGet、additionalInfoGet、boardListCycleGet、boardListGet、boardListGetStart、boardListGetStop、boardMessageCycleGet、boardMessageGet、boardMessageGetStart、boardMessageGetStop、boxStatusListGet、bsPowerSupplyGet、channelContractInfoGet、channelInfoGet、channelPhysicalInfoGet、channelPhysicalInfoGetStart、channelPhysicalInfoGetStop、downloadingPermissionGet、eventRelayInfoGet、localTimeOffsetInfoGet、mailInfoGet、mailListGet、parentalRatingPasswordGet、remoteInfoGet、remoteListGet

内容は、NAS 機能 (名前・ワークグループ・共有名・有効化)、DMP (DLNA プレーヤ) の登録管理、メール通知、掲示板 (board)、チャンネル物理情報、リモートアクセス登録、そして **FW 更新 (`updateFileDownload` / `updateFileUpload` / `updateProgressGet`)** までを含む。これは torne 単体の必要範囲を超えており、v1.00 時点の PVR WebAPI ライブラリが **nasne WebAPI の全面を定義する共有ライブラリ** だったことを示す (解釈)。torne Vita 自身がこの全てを使ったかは、定義の存在からは決まらない。

v2.02 ではこの独自分はテーブルからほぼ全て削除され、`config/remoteRegister` のみがテーブル外の SVRCONFG 隣接文脈 (サーバ設定レコードの項目定義とみられる位置) に残る。共有ライブラリが torne の実用範囲に刈り込まれた経過が、テーブル規模 (109 → 56) の変化に表れている (解釈)。

### 3.4 自作クライアントへの含意

iOS 版解析 ([21](21_torne_mobile_ipa_static_analysis.md)) が一次資料だった WebAPI 仕様について、本解析で (a) Vita 版も同一の WebAPI を使うこと、(b) 定義テーブルという形で JSON キー名とエンドポイントの対応が両プラットフォーム共通の PVR 層に存在すること、(c) v1.00 のテーブルが 62 件を超える全面定義を含むこと、が確定した。将来の自作クライアントでは、エンドポイント一覧の母集団として v1.00 テーブル (109 件) が最も広く、実働範囲の確定には動的観測が別途必要である。

## 4. その他の通信要素

### 4.1 発見 (SSDP) と UPnP

- SSDP 探索は iOS 版と同設計 (事実): `"ssdp:discover"`、`ST: urn:schemas-upnp-org:device:MediaServer:1`、`M-SEARCH * HTTP/1.1` テンプレート、`LookupDeviceBySSDP`、Telepathy 側の `Boot.Device.SSDPMSearch*` 設定キー群が両版にある。UPnP スタックの User-Agent は `Telepathy/1.0 UPnP/1.0 TpSsdp/1.0`。
- UPnP サービス URN は iOS 版と同一 (事実): `urn:schemas-upnp-org:service:ContentDirectory:1` (相当の文字列)、`urn:schemas-s-bras-org:service:X_PvrControl:1`、`urn:schemas-xsrs-org:service:X_ScheduledRecording:2`、`urn:schemas-xsrs-org:service:X_ScheduledRecordingExt:1`。
- 一方、iOS 版 torneplus にあった **SOAP アクションのテンプレート文字列 (Browse の引数埋め込み文) と、ポート 60151 の ObjID 形式 URL テンプレート (`http://%s:60151/ObjID=...IFO_PS...`) は、Vita の 4 ELF のどこにも無い** (文字列範囲の陰性)。Vita 側のリクエスト組み立ては汎用書式 (`http://%s:%d%s`、`http://%s:%d/%s`) によるコード駆動とみられる (解釈)。DLNA のヘッダ名 `transferMode.dlna.org` は eboot2 にある。
- ポート番号 `60151` / `58890` / `64210` は Vita でも文字列として存在しない (iOS 版の 64210 と同じく、数値定数か発見経路の記述から得る形とみられるが未同定)。

### 4.2 コンテンツ取得とウェブビデオ

- DIDL 内の DTCP 情報キー `DTCP1HOST=` / `DTCP1PORT=` / `DTCP1RAPORT=` / `DTCPDevID` は Vita にもあり (事実)、転送メタデータから AKE 接続先を得る DTCP-IP の標準形は iOS 版と共通する。
- ウェブビデオの URL テンプレートが両版にある (事実): `http://%s:%u/web/video/PvrAll/pvr?id=%s&quality=%s`。iOS 版 PvrBgApp のテンプレート ([21](21_torne_mobile_ipa_static_analysis.md) §3.4) には無かった **`&quality=%s` が Vita 側にはある**。
- ライブ視聴側のテンプレート `http://%s:%u/web/video/LiveTuner/%s/ch?nid=%x&tsid=%x&svid=%x&quality=%s` もあり (v1.00 では末尾が `quality=mobile` 固定)。[21](21_torne_mobile_ipa_static_analysis.md) の iOS 解析ではこの形式は記録されておらず、Vita 側で実在を確認した形である (iOS 側に存在しないことまでは主張しない)。
- nasne HOME: `http://127.0.0.1:%u/nasne_home/index_mobile.html` は iOS 版と同一のテンプレートがある。
- **nasne の更新情報チェック先** `http://ps-peripheral.dl.playstation.net/ps-peripheral/nasne/updateInfo.txt` が eboot / eboot2 の両方・両版にある (事実)。[21](21_torne_mobile_ipa_static_analysis.md) の iOS 解析には無い文字列で、Vita 版は PlayStation の周辺機器サーバから nasne の更新情報を取得する経路を持つ。

### 4.3 認証

- **`X-DTVToken` の文字列が Vita の 4 ELF 全てにある** (app eboot 3 件、patch eboot 2 件、eboot2 各 1 件の出現)。iOS 版では 3 バイナリとも存在しなかった ([21](21_torne_mobile_ipa_static_analysis.md) §3.2) ため、これは文字列レベルで確認できる両版の差である。Vita 版の WebAPI クライアントは認証ヘッダ名を平文で保持する。
- `config/PINVerify` は両版共通で存在する (§3.2)。トークンの算出形式そのものは文字列解析の範囲では決まらない (未確定、iOS 版と同じ制約)。

### 4.4 リモート視聴 (Telepathy)

- レゾルバ `http://tp-resolver.ndmdhs.com/trs/` は iOS 版と同一 (事実)。URN は `urn:schemas-sony-com:device:TelepathyDevice:%u` / `urn:schemas-sony-com:service:X_Telepathy:%u` (バージョンが書式指定子)。
- v2.02 の eboot には Telepathy SDK のビルドパスが残る: `D:\Telepathy\TelepathyDeviceSDK-1.3.5.1-33e6095-psvita-20140826-33\...` — **TelepathyDeviceSDK 1.3.5.1 (2014-08-26 ビルド)** が Vita 版のリモート視聴基盤である (事実)。
- DlnaProxy の設定キー群 (`Boot.Device.DlnaProxy*`) と P2P セットアップの計測ログ (`::TIME:: P2P_SETUP DTCP_LISTEN` / `DTCP_PING` / `DTCP_PING_OR_LISTEN`) は iOS 版と同系で、リモート時も AKE がエンドツーエンドに行われる設計の痕跡は共通する。

## 5. 資格情報 (DTCP-IP) の入手経路 — システムスタックの確定

### 5.1 DTCP スタックの所在: システムライブラリ SceDtcpIp

- eboot / eboot2 とも (両版) **`libSceDtcpIp` を import する** (import スタブ名 `libSceDtcpIp_stub` の実在、事実)。SceDtcpIp は Vita のシステムソフトウェアが提供する DTCP-IP ライブラリであり、AKE を含む DTCP-IP スタックはアプリではなくプラットフォーム側にある。
- アプリバイナリ内の陰性 (4 ELF の文字列範囲、事実): Sony DTCP-IP Middleware「DEWEY」のバナーは無い。iOS 版 DEWEY の AKE クラス群 (SdiSinkAuthentication、SdiReqCHALL 等) の名前は 0 件。DTCP-IP の HTTP 拡張ヘッダ (`Range.dtcp.com` 等) も、DLNA プロファイル名 (`DTCP_AVC_TS_JP_AAC_T` 等) も無い。これらはシステムライブラリ側に閉じていると読める (解釈)。
- アプリ側にあるのはラッパ層である (事実): `LoadDtcpIpUtility`、`DlnaClientDtcpIpUtilityWrapper`、`DTCPIPUtil`、`PrepareDtcpIp`、`ActivateDtcpIp`、`CheckActivationDtcpIp`、`CancelActivateDtcpIp`、`GetDTCPStatus`、`GetDTCPClientLibHandle`、`TpDTCPGetDTCPDevID` 等。命名は iOS 版 AVBase のラッパ (`CDtcpIp*`、`ActivateDtcpIp`、`CheckActivationDtcpIp`、`PrepareDtcpIp`、`LoadDtcpIpUtility`、[21](21_torne_mobile_ipa_static_analysis.md) §4.2) と重なっており、**AV フレームワークのラッパ層は両プラットフォーム共通だが、その背後のスタックが異なる** (iOS = アプリ同梱の DEWEY / CDtcpIp、Vita = システムの SceDtcpIp) という構図が確定した (解釈)。
- **`param_tbl`・`ur0`・`dtcp/` のパス文字列はアプリの 4 ELF のどこにも無い** (事実)。アプリは `ur0:/dtcp/param_tbl.enc` を直接参照せず、パラメータへのアクセスは SceDtcpIp の内側で完結する。[39](39_torne_vita_static_analysis.md) §6.2 の配置観測 (サンドボックス外のシステム領域に 1 件だけ存在) と完全に整合する。

### 5.2 アクティベーションと SEN/PSN 連携

- アクティベーションはラッパ API (`ActivateDtcpIp` / `CheckActivationDtcpIp`) と UI ([40](40_torne_vita_pfs_decrypted_analysis.md) §5.2 の `msg_psv_dtcpip_activate_*`、`dialog_setting_dtcp_ip_1`) でアプリ側に現れるが、**通信先やプロトコルを特定できる文字列はアプリ内に無い**。システムライブラリ / NP サービス側で処理されるためとみられる (解釈)。通信先の同定は本資料の範囲では未確定。
- SEN/PSN 連携はシステムの NP ライブラリ経由である (事実): import に `libSceNpManager`、`libSceNpCommon`、`libSceNpTus` があり、iOS 版 torneplus に埋め込まれていた PSN OAuth エンドポイント (`auth.api.sonyentertainmentnetwork.com` 系) は Vita の eboot に無い。Vita 側の OAuth 文字列は Twitter / ニコニコ実況向けのみである。
- **TUS (Title User Storage) の利用**: `libSceNpTus` の import に加え、`PvrNetTusTimerRecordExecThread`、`PvrNetTusUnregisteredExecsFileExecThread` というスレッド名と、セーブデータ内の `tus_op_execs.dat` / `tus_non_op_execs.dat` ([39](39_torne_vita_static_analysis.md) §3) が対応する。タイマー録画の実行記録を PSN のタイトル共用ストレージ経由で同期する仕組みで、iOS 版の解析範囲には対応物が無い、PS プラットフォーム固有の経路である (解釈)。
- バージョン差: v1.00 の eboot は `libSceNpCommerce2` を import する (出現 30 件) が、v2.02 では 0 件で import から消えている (事実)。

### 5.3 経路の比較まとめ

| 項目 | iOS 版 | Vita 版 |
|---|---|---|
| DTCP-IP スタック | アプリ同梱 (PvrBgApp の DEWEY + AVBase の CDtcpIp) | **システムライブラリ SceDtcpIp** (アプリはラッパのみ) |
| AKE の実行主体 | アプリプロセス内 (CommonCrypto) | システム側 (アプリからはラッパ API 経由) |
| 資格情報の供給 | アプリ単位: GAE + App Store レシート → `PvrAssetData.cxml` → DAL #9/#13 | アプリ単位の資産ファイルは無し。プラットフォーム保持の `ur0:/dtcp/param_tbl.enc` をシステム側が使う |
| アプリから param テーブルへの参照 | (DAL 経由でアプリが扱う) | **無し** (パス文字列自体が無い) |
| アカウント束縛 | App Store / torne の GAE アカウント | SEN/PSN サインイン (システム NP ライブラリ)。TUS による録画実行記録の同期 |
| アクティベーション | 資産ファイルの取得が相当 | 専用手続きあり (UI + ラッパ API)。通信先はアプリ文字列から同定不能 |

## 6. Vita_App02 の関連データ — 棚卸しと差分

### 6.1 param_tbl.enc — 不変

`Vita_App02/ur0/dtcp/param_tbl.enc` は 368 バイト、SHA-256 `1f7c740e88f8a10452bdd113197a5ce5cd55aa7b97d0904eaf130968e8f911d2` で、[39](39_torne_vita_static_analysis.md) §6.2 の測定値と**完全一致**した (ハッシュ比較のみ実施し、中身は開いていない)。本人が nasne (公式 FW) の録画終了と Vita での再生までを回した後のコピーでもファイル内容が変わっていないことから、少なくとも録画・再生という通常利用ではこのテーブルは書き換わらない (事実としてハッシュ一致、書き換え有無の解釈は「同一内容への再書き込み」とは区別できない点に注意)。

### 6.2 umass — 本コピーに含まれず

Vita_App02 に umass コンテナは含まれていない。ウケトルネ書き出しや録画保存の実体ファイルが現れたかは本コピーでは観測できない ([39](39_torne_vita_static_analysis.md) §5 のコピーでは空だった、という既知のみ)。

### 6.3 セーブデータ — PFS 暗号化のまま、構成は不変

Vita_App02 のセーブデータは raw コピーで、`sce_pfs/files.db` のマジックは `SCENGPFS`、`Manage/PvrContent.db` 等に SQLite マジックは無く、ファイルサイズは 32 KiB 単位 — [39](39_torne_vita_static_analysis.md) §1.2 と同じ PFS 暗号化状態であり、内容の比較はできない (事実)。

ファイル構成は [39](39_torne_vita_static_analysis.md) §3 と同型で、`Manage/` (PvrContent.db 196,608 バイト = 前回と同じ表示サイズ、PvrGameConfig.cxml、PvrOperationLog.db)、`telepathy/` (TpStorage 6 件 + TpFlash 2 件)、`tus_op_execs.dat` / `tus_non_op_execs.dat`、`sql3work/`、`sce_sys/` が揃う。差分として観測できるのは次の点のみ:

- [39](39_torne_vita_static_analysis.md) で存在した `PvrContent.db-journal` が今回は無い (SQLite の一時ファイルであり、セッション状態による差とみられる)。
- `sql3work/` の一時ファイル名 (etilqs_*) はランダム名のため相違する。
- `sce_pfs/icv.db/` に .icv が 26 件ある (PFS の整合性検証データ)。

## 7. 未確定事項

- WebAPI の実リクエスト/レスポンス形式の完全な確定 (定義テーブルからキー名とパスの対応は読めるが、値の型・必須性・実送信範囲は動的観測か逆アセンブルが必要)。v1.00 テーブルの 109 件のうち torne Vita 自身が実際に使う範囲も未確定。
- WebAPI のポート (64210 とされる) の決定方法。Vita でも文字列に無く、数値定数か UPnP デバイス記述由来かは未同定 (iOS 版と同じ残件)。
- SceDtcpIp の内部実装 (AKE の詳細、`param_tbl.enc` の読み手・復号・生成/更新経路)。システムライブラリ側であり、本資料 (アプリ側コピー) の範囲外。
- DTCP-IP アクティベーションの通信先・プロトコル (アプリ文字列からは同定できなかった)。
- SOAP アクションや DMS 転送の実リクエスト形式 (iOS 版にあったテンプレート文字列が Vita には無く、コード駆動の組み立てを静的に追う作業は未実施)。
- umass への書き出し実績データの形式 (書き出し済みデータを含むコピーの調達が前提)。
