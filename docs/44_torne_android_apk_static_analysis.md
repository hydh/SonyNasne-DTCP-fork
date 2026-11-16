# torne Android 版 (公式 APK) の静的調査

**対象**: torne® mobile バージョン 1.50 の Android 版。APKPure で配布されている XAPK を本人が marnux `~/ダウンロード/torneMobileBackup/Android/` に配置したものを対象に、ファイルのみを静的解析した (2026-11-16 実施)。実機 (nasne / Android 端末) には接続していない。

**現在の到達点**: Android 版は iOS 版 ([21](21_torne_mobile_ipa_static_analysis.md)) とほぼ同型の構成だった — nasne WebAPI のパス文字列 63 件 (iOS の 62 件と共通 60 件、Android のみ chEpg 群 3 件、iOS のみ 2 件)、DTCP-IP スタックはアプリ内蔵の **DEWEY が libPvrBgApp.so に存在** (Vita のシステムライブラリ型ではない)、資格情報プロビジョニングも `PvrAssetData.cxml` + GAE の系譜で、レシート交換に相当する入力が App Store から Google Play Billing に置き換わっている (opAndroidPurchases)。一方で AVBase 側は AKE 実装を持たず、Vita 版アプリ層と同名のラッパ (LoadDtcpIpUtility 等) のみを持つ、という iOS と Vita の中間的な形も見えた。

> スコープ: 本調査は Vita 版調査 ([39](39_torne_vita_static_analysis.md)〜[41](41_torne_vita_fagdec_eboot_analysis.md)、[43](43_torne_vita_umass_export.md)) と同じ枠組みで、通信方式・API・資産の所在と形式という**構造レベルまで**である。資格情報 (証明書・秘密鍵・mobileId 等) の抽出、暗号化資産の復号、メモリ捕捉は行っていない。鍵の値や個体識別情報は記録しない (ハッシュのみ) という本リポの作法に従う。

## 1. APK の素性

### 1.1 配布物

| 項目 | 値 |
|---|---|
| ファイル | `torne®+mobile_1.50_APKPure.xapk` (XAPK 形式、xapk_version 2) |
| サイズ | 113,751,726 バイト |
| SHA-256 | `f032445e7fab25f97a1b937edb183f4bd2e18273361d67a5653f2907f51afaae` |
| ベース APK | `com.playstation.tornemobile.apk` (78,931,371 バイト) |
| 分割 APK | `config.arm64_v8a.apk` (34,816,694 バイト、ネイティブライブラリのみ) |
| パッケージ名 | `com.playstation.tornemobile` (iOS のバンドル ID と同一) |
| バージョン | versionName 1.50 / versionCode 2026072214 (iOS 版と同版数) |
| SDK | minSdk 32 (Android 12) / targetSdk 37 |

署名は、署名者証明書の SHA-256 ダイジェスト `a2a5373c32ea31266f2fd0b495721d97d378822f4869288d6ad48fc9439012d6` (DN は SCEA の QA 部門名義) と、Google の Source Stamp (Play 配布の印) の 2 系統を確認した。APKPure 経由で入手した配布物であるため、出所の確度はその配布経路に依存する点に留意する。

権限で特記すべきもの:

- `com.sony.snei.np.android.account.provider.permission.DUID_READ_PROVIDER` — Sony の NP アカウントプロバイダから DUID を読む権限 (§6)
- `com.android.vending.BILLING` / `com.android.vending.CHECK_LICENSE` — Play 課金とライセンス確認 (§6)
- `android.permission.NEARBY_WIFI_DEVICES` / `ACCESS_LOCAL_NETWORK` / `CHANGE_WIFI_MULTICAST_STATE` — LAN 内発見 (SSDP マルチキャスト含む)
- `android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK` — 再生系フォアグラウンドサービス

### 1.2 ネイティブライブラリ (config.arm64_v8a.apk 内、arm64-v8a)

| ライブラリ | サイズ (バイト) | 役割 (本調査の同定) |
|---|---|---|
| libPvrMain_plus.so | 11,520,304 | 本体 (iOS の torneplus 相当)。WebAPI パス文字列の大半と GAE 系 op を保持 |
| libAVBase.so | 10,815,792 | AV 基盤。DTCP はラッパ層のみ (§5) |
| libPvrBgApp.so | 4,032,816 | バックグラウンド側。DEWEY と資格情報資産の読み手 (§5・§6) |
| libTpMasterAndroidJNI.so | 3,824,232 | Telepathy マスタ (§7) |
| libtelepathyjni.so | 3,619,184 | Telepathy JNI (§7) |
| libpairipcore.so | 609,416 | PairIP (コード保護) |
| libscecompanionutil.so | 252,448 | PSN 連携ユーティリティ (companionutil) |

リンク関係 (DT_NEEDED): libPvrMain_plus.so が libAVBase / libPvrBgApp / libtelepathyjni / libscecompanionutil の全てをリンクするハブ構造。libAVBase と libPvrBgApp は互いを DT_NEEDED に持たない。

### 1.3 資産 (ベース APK の assets/)

- `PvrResource.cxml` (12,029,632 バイト)、`PvrTheme.cxml` (6,025,456 バイト、テーマ別に THEMEDIR 配下にも同名ファイル)、`PvrVersionHistory.cxml`、`NicoJkResource.cxml`、`TwitterResource.cxml` — iOS/Vita と同系のリソース群
- `initialContent.db` (366,592 バイト) — iOS でコンテンツカタログの初期 DB と同定された同名資産 ([33](33_torne_credentials_provisioning.md))。ただし Android 版は先頭から高エントロピーで**平文の SQLite ではない** (SQLite として開けないことを実測)。形式は未確定 (§8)
- `TelepathyDeviceConfig.bin` と `TpDevConfig.dat` (各 12,272 バイト) — MD5 が一致しバイト同一
- `ca-bundle.crt` (PEM 証明書束)、`GCRESOURCEDIR.psarc`、BGM (mp3 群)、ARIB フォント (`SCE-ShinmarugoR_ARIB.ttf` 他)
- ランダムな名前 (16 文字) の資産が約 20 件あり、いずれも形式不明の不透明データ (iOS 版にもあった難読化命名と同じ作法)
- `assets/shaders/` には iOS 名のシェーダマクロ (`FragmentShaderMacro_iOS.h` 等) が残っており、描画層がプラットフォーム間で共有されている痕跡がある

### 1.4 DEX とコンポーネント

- DEX は `classes.dex` 1 本のみ (2,929,960 バイト)。Java/Kotlin 層は薄く、アプリ固有分は `com.playstation` (568 クラス) と `com.playstation.companionutil` (295 クラス)、`com.sony.snei.np.android.sso` (PSN SSO クライアント) が中心で、残りは AndroidX / Google Play services / Material 等のライブラリ。本体ロジックはネイティブ側にある (iOS と同じ非対称)。
- Application は PairIP の `com.pairip.application.Application` (コード保護の入口)。
- 主要コンポーネント: `com.playstation.tornemobile.MainActivity` / `WebViewActivity` / `OskActivity`、`background.ExportContentService` (映像書き出し、§8)、`com.sony.telepathy.system.android.TpMasterAndroidService` (§7)、companionutil のサインイン・発見・PassCode/PinCode 系 Activity 群、Play Billing の `AppBillingHelper` (JNI 経由)。

## 2. nasne WebAPI の実装比較

### 2.1 Android 版のパス文字列 63 件

`group/name` 形式のパス文字列は **libPvrMain_plus.so に 63 件**が集中していた (libPvrBgApp.so 側にも 13 件のサブセット、§2.3)。内訳:

- **config/ (17 件)**: HDDRegister、HDDRegisterProgressGet、HDDRelease、PINVerify、areaInfoSet、boxNameSet、channelScanCancel、channelScanProgressGet、channelScanStart、currDateSet、dtcpipClientStop、finishSetup、internalHDDInitialize、internalHDDInitializeProgressGet、mobileBitrateInfoSet、parentalRatingInfoSet、recNgListDelete
- **recorded/ (13 件)**: PMTMapGet、SEMapDataGet、recordedContentAdditionalInfoGet、recordedContentAdditionalInfoSet、recordedContentChpDataGet、recordedContentCountGet、recordedContentMaxCountGet、recordedContentResumePositionSet、recordedContentThumbnailGet、thumbnailMapGet、titleDelete、titleListGet、titleUpdate
- **schedule/ (6 件)**: conflictListGet、reservedInfoBitrateGet、reservedInfoCreate、reservedInfoDelete、reservedInfoUpdate、reservedListGet
- **status/ (24 件)**: BCASInfoGet、CAMsgInfoGet、EMMMsgInfoGet、EPGVersionInfoGet、HDDInfoGet、HDDListGet、areaInfoGet、boxNameGet、channelListGet、currDateGet、dmsStreamStopReasonListGet、dtcpipClientListGet、dtvtunerDeviceInfoGet、isFinishSetup、liveStreamPCRGet、liveStreamStatusListGet、mobileBitrateInfoGet、multiTunerLiveStreamStatusListGet、networkIfInfoGet、parentalRatingInfoGet、recNgListGet、requestClientInfoGet、softwareVersionGet、updateCheck
- **chEpg/ (3 件)**: EITPFGet、EPGGet、channelLogoDataGet

### 2.2 iOS 版 62 件・Vita 版との突き合わせ

iOS 版の 62 件 ([21](21_torne_mobile_ipa_static_analysis.md) §3.2) との差分:

- **共通: 60 件**
- **Android のみ: chEpg 群 3 件** (EITPFGet / EPGGet / channelLogoDataGet)。iOS の 62 件にも Vita 2.02 の定義表 56 件 ([41](41_torne_vita_fagdec_eboot_analysis.md)) にもこの群は無い。ただし iOS 側の 62 件は「PvrNasneWebAPI が使う分」として抽出された集合であり、chEpg 群が iOS バイナリの別経路 (EPG 取得専用の仕組み等) に存在するかは [21](21_torne_mobile_ipa_static_analysis.md) の記録範囲外で、未確定とする。
- **iOS のみ: 2 件** — `schedule/reservedListGet2` と `status/liveStreamPCRGet2`。いずれも「第 2 版」の取得系で、Android の文字列には裸名でも存在しなかった。

Vita 2.02 の 56 件との関係では、Android の集合は Vita の 56 件から liveStreamPCRGet2 を除いた 55 件を全て含み、さらに「iOS のみ」とされた 6 件のうち 5 件 (recordedContentCountGet / recordedContentMaxCountGet / dtvtunerDeviceInfoGet / multiTunerLiveStreamStatusListGet / requestClientInfoGet) と chEpg 群 3 件を加えた形になる。つまり 3 プラットフォームの中で Android の文字列集合が最も広い (63 件)。Vita v1.00 の全面定義 109 件 ([41](41_torne_vita_fagdec_eboot_analysis.md)) との突き合わせは、Android 側に定義テーブル形式 (JSON キーとパスの対) が見つからなかったため行っていない (Android はパス文字列そのものが埋め込まれている形で、Vita のような独立した定義テーブルは文字列解析の範囲では確認できなかった)。

### 2.3 libPvrBgApp.so 側のサブセット 13 件

バックグラウンド側にも次
...[truncated 6593 chars]

## 訂正 (docs/46)

§2.1 の WebAPI パス文字列の件数と内訳には誤りがあった。docs/46 の再走査 (本書と同じ libPvrMain_plus.so 実物) では 65 件が数えられ、「iOS のみ」とした `schedule/reservedListGet2` と `status/liveStreamPCRGet2` の両文字列が libPvrMain_plus.so 内に存在した。したがって内訳は「Android の 65 件は iOS の 62 件を全て含み、Android のみは chEpg 群 3 件のみ、Vita 2.02 の 56 件も文字列レベルでは全て含む」が正しい。両文字列が実 endpoint として呼ばれるかは未確定のままである。詳細は [46](46_torne_codex_work_review.md) §2.1 を参照。
