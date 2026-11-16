# 39. torne PlayStation®Vita 版 (PCSC00025) の静的調査 — iOS 版との通信・資格情報経路の比較

PS Vita 版 torne (タイトル ID `PCSC00025`) のコピー済みストレージを静的に調査し、torne mobile (iOS 版、[21](21_torne_mobile_ipa_static_analysis.md) / [33](33_torne_credentials_provisioning.md)–[36](36_torne_cxml_disk_format.md)) との比較を行った記録 (2026-11-16 実施)。対象は marnux 上のコピー (`~/ダウンロード/VitaStorage/`) のみで、実機 (nasne / Vita 本体) には触っていない。資格情報については入手経路の調査のみで、鍵素材そのものの抽出・復号・導出は行っていない (特に `ur0/dtcp/` は棚卸しレベルに留めた)。

**現在の到達点**: 本コピーは **PFS 暗号化されたままの raw コピー**であり、アプリ本体 (eboot.bin) を含むペイロードは全て暗号化されていて文字列・シンボル解析は不可能だった (SELF か ELF かの判定自体ができない)。そのため nasne WebAPI のエンドポイント単位の突き合わせは本コピーでは**未確定**である。一方、平文で読める範囲 (param.sfo、LiveArea 定義、ディレクトリ構造、ファイル名) からは、(1) リソース・DB の命名が iOS 版の「PVR」プラットフォームと同系であること、(2) Telepathy 永続ストレージが iOS 版と同型に存在すること、(3) **資格情報の置き場所が iOS 版と構造的に異なる**こと — iOS 版のようなアプリ単位の暗号化資産ファイル (`PvrAssetData.cxml`) は存在せず、代わりにシステム領域 `ur0:/dtcp/param_tbl.enc` (368 バイト、OpenSSL の Salted 形式) がタイトルのサンドボックス外に存在すること — が分かった。

## 1. 対象と方法

### 1.1 対象の同定

- コピー元: PS Vita (Vita 2000 系) のストレージ。`ur0/` = 本体内蔵ストレージ (コピー総量 147 MB)、`ux0/` = 外部ストレージ (独自形式 SD、同 7.1 GB)。
- torne 本体: `ux0/app/PCSC00025/` (52 MB) と更新パッチ `ux0/patch/PCSC00025/` (18 MB)。セーブデータ: `ux0/user/00/savedata/PCSC00025/` (1.3 MB)。
- バージョン (param.sfo の平文読み、事実):
  - ベースアプリ: TITLE = 「torne™ PlayStation®Vita」、APP_VER = **01.00**、CATEGORY = `gdc`、CONTENT_ID = `JA0003-PCSC00025_00-TORNEVITA0000000`、PSP2_DISP_VER = 02.020、PUBTOOLINFO = `c_date=20121207, sdk_ver=02000000` (2012-12-07 ビルド、SDK 2.0)。
  - パッチ: APP_VER = **02.02**、CATEGORY = `gpc`、PSP2_DISP_VER = 03.650、PUBTOOLINFO = `c_date=20171201, sdk_ver=03570000` (2017-12-01 ビルド、SDK 3.57)。すなわち本コピーの実効バージョンは **2.02**。
- アプリのライセンス: `ux0/license/app/PCSC00025/` に 512 バイトの `.rif` が 1 件存在する (ファイル名は記録しない)。アプリ自体は PSN ライセンスで配布される形 (事実)。これはアプリ本体のライセンスであり、DTCP 資格情報とは別物である。

### 1.2 コピーの性質 — PFS 暗号化 (本調査の最大の制約)

本コピーは Vita 本体の PFS 層を通していない raw コピーであり、アプリ/パッチ/セーブデータのペイロードは PFS 暗号化されたままである。根拠 (事実):

- `sce_pfs/files.db` のマジックが `SCENGPFS` で、PFS メタデータがそのまま含まれている。
- 平文のはずのファイルが全て高エントロピーで本来のマジックを持たない: `version.txt`、`channelList.bin`、電子マニュアルの PNG (PNG マジックなし)、`sce_sys/icon0.png`、LiveArea の `template.xml` (アプリ側コピー) 等。
- セーブデータ側も同様で、`Manage/PvrContent.db` に SQLite マジックは無く、`telepathy/` 配下も含め全て暗号化されている。セーブデータのファイルサイズが全て 32 KiB の倍数なのは PFS の割り当て単位に丸められた表示であり、実サイズは不明。
- 平文で読めたのは `sce_sys/param.sfo` (アプリ/パッチとも) と、`ur0/appmeta/PCSC00025/` 側の LiveArea 定義・画像のみ。

したがって **eboot.bin の可読性は「不可」** である:

| ファイル | サイズ | SHA-256 | 状態 |
|---|---|---|---|
| app/eboot.bin (v1.00) | 4,109,536 | `7328082ddbe4c069c66922d9156232929e2433104f849b7182094ed6d5a5c0f7` | PFS 暗号化 |
| patch/eboot.bin (v2.02) | 5,978,096 | `46bd6dc8cc6f65fc1abc83fc580c421027ddb9302a08ae7511315f3621e93c06` | PFS 暗号化 |
| app/eboot2.bin | 135,536 | `18d75eb8485d12b82762b57a508486d6c74c85fa77b67abe03a27d7ce57f8721` | PFS 暗号化 (役割は未同定) |
| patch/eboot2.bin | 164,784 | (未採取) | PFS 暗号化 |

SELF ヘッダ (`SCE\0`) か復号済み ELF (`\x7fELF`) かの判定自体ができず、strings / シンボル解析は実施不能だった。以下、通信方法については平文資料と構造からの間接証拠に限って記述し、直接証拠が無い点は未確定と明記する。

### 1.3 方法

- ディレクトリツリー・サイズ・マジックの棚卸し、param.sfo のパース (自前パーサ)、LiveArea `template.xml` (appmeta 側平文) の実読、umass イメージの読み取り専用リスト (7z による FAT32 の展開表示。マウント・書き込みはしていない)。
- `~/ダウンロード/pic` には Vita の識別子らしき画面写真 5 件 (61,494–80,630 バイト) があるが、機器を特定する値は読み取らず記録もしない。セーブデータ側 param.sfo に `ACCOUNT_ID` キーが存在することだけを確認し、値は読んでいない。

## 2. アプリ構成 (棚卸し)

Vita 版は単一 eboot 型で、iOS 版のような独立フレームワーク (AVBase / PvrBgApp) は存在しない。`sce_module/` にあるのはシステムランタイムの `.suprx` (libc / libfios2 / libult) と `sce_sys/about/right.suprx` のみで、アプリ固有のモジュールファイルは無い (事実)。リソース類は iOS 版と同名のものが揃う (いずれも PFS 暗号化で中身は読めない):

- `PvrResource.cxml` (ベース 2,432,304 / パッチ 2,489,088 バイト)、`PvrTheme.cxml` (同 3,866,528 / 3,845,632)、`PvrVersionHistory.cxml`、`NicoJkResource.cxml` (パッチ側)、`PvrBgAppResource.txt`、`channelList.bin`。
- `TelepathyDeviceConfig.bin` はパッチ側に 9,072 バイト (iOS 版バンドルは 12,272 バイト。同名だがサイズは異なる)。
- `initialContent.db` (パッチ側 15,360 バイト。iOS 版バンドルは 366,592 バイトで平文 SQLite でないことが確定済み)、`initialOperationLog.db` (パッチ側 16,384 バイト)。

## 3. セーブデータ構造 (iOS 版コンテナとの対応)

`ux0/user/00/savedata/PCSC00025/` の構成 (事実、全て PFS 暗号化):

- `Manage/`: `PvrGameConfig.cxml`、`PvrContent.db` (カード上 196,608 バイト)、`PvrContent.db-journal`、`PvrOperationLog.db`。
- `telepathy/00000000000000000000000000000000/`: `TpStorage000.bin` / `001` / `100` / `101` / `102` / `103`、`TpFlash0.bin` / `TpFlash1.bin` (各 32,768 バイト表示)。
- その他: `sql3work/` (SQLite の一時ファイル残骸 = SQLite を使用している傍証)、`tus_op_execs.dat` / `tus_non_op_execs.dat`、`USER.CNF`、`sce_sys/` (param.sfo / sealedkey / safemem.dat / sdslot.dat / keystone)。

iOS 版との対応 (事実 + 解釈): `PvrContent.db` / `PvrOperationLog.db` という DB 命名と `Manage/` ディレクトリは iOS 版の構造 ([36](36_torne_cxml_disk_format.md) で言及された Manage 配下) と共通し、Telepathy の永続ストレージ (`TpStorage*` / `TpFlash*`) も iOS 版の実機採取 ([38](38_torne_se_live_session.md)) と同型である。両プラットフォームが同じ「PVR」プラットフォームコードベースの移植であることを構造面から裏付ける (解釈)。

## 4. nasne との通信方法 — iOS 版との比較

### 4.1 直接比較は本コピーでは不能 (未確定)

iOS 版では torneplus の文字列から nasne WebAPI のエンドポイント 62 件 (config/ 17、recorded/ 13、schedule/ 7、status/ 25) を全数抽出できた ([21](21_torne_mobile_ipa_static_analysis.md) §3.2)。Vita 版については eboot が読めないため、**WebAPI エンドポイント・UPnP/SOAP テンプレート・ポート番号 (60151 / 58890 / 64210 等) のいずれも直接証拠が無く、API 単位の同一/相違は判定できない**。Vita 版が nasne WebAPI を使うかどうか自体、本コピーからは確定できない。

### 4.2 間接証拠

- **コードベースの同系性**: §2・§3 のとおり、リソース (Pvr*.cxml) と DB (PvrContent.db / PvrOperationLog.db / initialContent.db) の命名体系が iOS 版と一致する。iOS 版の WebAPI クライアントは `PvrNasneWebAPI` という PVR 側の構成要素であり、Vita 版も同じ PVR 基盤の上で nasne 通信 (録画一覧・予約・ライブ視聴) を実装している可能性が高い (解釈。エンドポイントの同一性は未検証)。
- **リモート視聴 (Telepathy)**: Vita 版のセーブデータにも Telepathy 永続ストレージが同型に存在し、パッチには `TelepathyDeviceConfig.bin` と `telepathy/` アイコンリソースが含まれる。iOS 版と同様、リモート視聴は Telepathy 基盤で行われる設計とみられる (解釈)。
- **LiveArea の外部リンク** (appmeta 側 `template.xml` の平文、事実): `http://torne.scej-online.jp/`、`https://tv.so-net.ne.jp/chan-toru/` (So-net のリモート予約 Web サービス「チャン・トル」)、`http://torne.jp/`、PlayStation 公式の torne 紹介ページ、PS Store のブラウズ (`psts:browse?category=JA0003-PCSC00025_00-TORNEVITA100`)。これらは LiveArea からの Web リンクであり、アプリ内 API ではないが、Vita 版の時代の周辺サービス構成を示す。
- **録画の持ち出し (ローカル保存)**: §5 の umass コンテナに `TORNE/recording` ディレクトリが用意されており、Vita 版には nasne の録画をローカルストレージへ保存する機能がある (ディレクトリ名からの解釈)。保存ファイルの形式はコンテナが空のため観測できなかった。

## 5. umass コンテナ (録画保存先と推定される FAT32 イメージ)

`ux0/umass/98D0C1F1…C72.img` (ファイル名は 16 進 32 文字) は 4,294,967,296 バイト (ちょうど 4 GiB) の FAT32 イメージ (クラスタ 32 KiB)。読み取り専用でリストした内容 (事実):

- ディレクトリ: `SceIoTrash`、`MPE_ROOT`、`TORNE`、`TORNE/recording`、`TORNE/unpromoted`。
- ファイルは **0 件**、空き容量 4,293,853,184 バイト (使用量は FAT 構造分のみ)。すなわち本コピーでは録画保存先として初期化されただけで、録画は保存されていない (または削除済み)。
- `TORNE/unpromoted` という命名はそのまま記録する (DTCP の文脈での意味づけは本資料からは確定できない)。
- タイムスタンプは 2026-08-04 (本体時計ベース)。

## 6. 資格情報 (DTCP-IP) の入手経路 — iOS 版との比較

### 6.1 iOS 版の経路 (既存確定事項の要約)

iOS 版はアプリ単位の供給である ([33](33_torne_credentials_provisioning.md)–[36](36_torne_cxml_disk_format.md)): torne の GAE バックエンドが App Store レシートと引き換えにライセンス応答を返し、その暗号化資産が `PvrAssetData.cxml` としてアプリの Documents に保存される。復号鍵はインスタンス固有 (mobileId + キーチェーン UUID から導出) で、復号された TLV が DAL アイテムストアの #9 (デバイス証明書) / #13 として DTCP-IP ミドルウェア DEWEY に渡る。

### 6.2 Vita 版で観測された事実

- **`PvrAssetData.cxml` は VitaStorage 内のどこにも存在しない** (ファイル名検索で 0 件)。アプリ/パッチ/セーブデータのどこにも、資産ファイルに相当する名前のファイルは無い。
- 代わりに、**`ur0:/dtcp/param_tbl.enc` が 1 件だけ存在する**: 368 バイト、SHA-256 `1f7c740e88f8a10452bdd113197a5ce5cd55aa7b97d0904eaf130968e8f911d2`。先頭は OpenSSL の salted 形式 (`Salted__` + ソルト 8 バイト + 暗号文 352 バイト = AES 22 ブロック分)。**中身の復号は本調査の範囲外として実施していない** (棚卸しレベルまで)。
- 置き場所が決定的に異なる: `ur0:/dtcp/` は本体内蔵ストレージのシステム側領域で、どのタイトルのサンドボックス (ux0/app・savedata) の外にある。
- セーブデータ側に資格情報らしい名前のファイルは無い (`Manage/` は設定・コンテンツ DB・操作ログのみ)。ただし全ファイルが PFS 暗号化されているため、内容面での不存在までは主張できない (ファイル名レベルの観測に限る)。

### 6.3 解釈

Vita 版の DTCP パラメータは、iOS 版のような「アプリごとの暗号化資産をサーバから受け取る」形ではなく、**プラットフォーム (システムソフトウェア) 側が `ur0:/dtcp/` に保持するパラメータテーブルをアプリが利用する形**と読める (配置からの解釈)。torne Vita の AKE 処理がシステムの DTCP スタックで行われるのか、eboot 内の実装 (DEWEY 相当) がこのテーブルを参照するのかは、eboot が読めないため未確定である。`param_tbl.enc` の生成・更新経路 (工場出荷時か、システムソフトウェア同梱か、初回利用時のプロビジョニングか) も本コピーからは判明しない。形式が OpenSSL salted 形式である点は、iOS 版の独自コンテナ形式 (ランダム 16 バイト + SHA-256 + ペイロード、[36](36_torne_cxml_disk_format.md)) とも異なる、汎用形式の採用を示す (事実として形式のみ)。

## 7. 未確定事項

- Vita 版 eboot の PFS 復号済みコピーが得られれば、strings で iOS 版 62 エンドポイントとの突き合わせ、UPnP テンプレート・ポート・User-Agent の確認が可能になる (本調査では未実施。復号済みコピーの調達は今後の課題)。
- Vita 版が nasne WebAPI を使うかどうかの直接証拠、予約作成・番組表取得の具体的な API 形。
- `param_tbl.enc` の生成・更新経路と、Vita 版 AKE の実行主体 (システムスタックかアプリ内蔵か)。
- `eboot2.bin` の役割。
- umass コンテナへ実際に録画を保存した際のファイル命名・形式 (本コピーでは空)。
- バージョン履歴: ベース 1.00 (2012-12) からパッチ 2.02 (2017-12) の間の中間バージョン (`PvrVersionHistory.cxml` は暗号化で読めない)。
