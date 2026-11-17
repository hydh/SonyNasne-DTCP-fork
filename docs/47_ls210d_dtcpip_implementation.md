# 47 Buffalo LS210D の DTCP-IP 実装調査 (DiXiM スタック)

対象: Buffalo LinkStation LS210D (DTCP-IP 対応 NAS)。nasne / torne 以外の市販 DTCP-IP 製品の実装調査であり、本リポジトリの主対象である nasne 側の DTCP 理解 (特に AKE の実装形態と資格情報プロビジョニング) への参照資料として記録する。調査は、ファームウェア (FW) の静的解析、ダウンロードモジュールの実物回収と逆アセンブル、実機での照合の 3 段で行った。

状態: **AKE のコマンド体系・暗号構成・資格情報の所在と供給経路は確定。** DTCP-IP の実体は DiXiM スタック (dms_sync / libdixim_drm.so) で、デバイス証明書・秘密鍵は SPI フラッシュ内のレコード表に置かれ、Buffalo 製 libhermit.so が汎用 stdio で読み出して AKE エンジンへ供給する。Kx 導出の詳細と有効期限の数値、Kc 配送形式の詳細、使用 ECC 曲線のコード上の選択箇所、ペアでない側の鍵レコードの役割は未確定 (§9)。pydtcpip の `DeviceCredentials` 検証との整合性 (§7) は、2026-11-17 に本人が実値で検証を実施して成功し、同一ペアでの実機 nasne との AKE 実走も成功している (docs/48・49)。

範囲と作法: 鍵・証明書・秘密鍵の生値は読んでいない・記録していない (所在・形式・長さ・読み込み手順のみ)。実機フラッシュへのアクセスは読み取りによるバックアップ取得のみで、本調査の解析作業ではレコードの復号は行っていない (2026-11-17 に本人が行った検証については §7・§8)。個体を特定できる値 (機器 ID、シリアル等) も記録していない。

## 1. 対象製品と全体像

- LS210D は LinkStation 200 シリーズの 1 ベイ NAS。製品 ID (PID) は `0x0000001D`。実機のカーネルは 3.3.4 (公式 FW)。
- 調査は FW 1.84 のパッケージ解析から開始し、実機照合の時点では実機がオンライン更新で FW **1.86-0.07** (2025/09/29 ビルド) へ更新されていた。DiXiM モジュールの実物は 1.86 の rootfs から回収した。
- DTCP-IP の有効化ゲートは機種定義 `.nas_features` の `SUPPORT_DTCP_IP=1` で、日本向け 10 機種のみ 1 (LS210D を含む。LS-CHL (PID `0x00000012`) は例外として除外される)。
- DLNA サーバは TwonkyServer 7.1.1-dsd (HTTP 9050) と DiXiM の 2 経路があり、LS210D の既定は `DLNA_SERVER="dixim"`。dixim 選択時は起動スクリプトが Twonky を除去する。
- **Twonky 経路の決着**: twonkyserver 内の `cb_dtcp_*` 全 64 個は関数ではなく `.bss` 上の関数ポインタ変数 (外部モジュールが埋めるコールバック表) で、コードが参照するのは 25 個のみ。AKE・セッション・CCI 系は参照ゼロで、暗号定数 (AES S-box、SHA-1/256、MD5、ECC、TEA) の走査もテーブル方式・即値方式とも全 0 件だった。ソフトウェア暗号実装が存在しないことの積極的証拠であり、**Twonky 側に AKE 実装は無い**。実体は DiXiM 側にある (本書の主題)。

DiXiM 経路の構成:

```
dms_sync (DiXiM DMS, C++)
  ├─ UPnP/HTTP サーバ (port 55247): CDS、HttpMediaTransport (contents/)
  ├─ dtcpbridge (dixim::dmsp::dtcp::dtcpbridge) … libdixim_drm の ddtcp_* を駆動
  └─ libdixim_drm.so
       ├─ ddtcp_* … DTCP AKE エンジン (コマンド処理、Kx/Kc 管理、RSR)
       ├─ ddrm_*  … DRM メディアフィルタ (PCP 暗号化/復号、Move、cipher_file 連携)
       ├─ LibTomCrypt (静的リンク) … AES-CBC / SHA-1 / ECC
       ├─ /dev/crypto (cryptodev) … AKE 鍵交換まわりの一部
       ├─ MB86M01 ドライバ (/dev/m01fmb0) … トランスコード連携のみ
       └─ libhermit.so (Buffalo 製) … SPI フラッシュの鍵金庫
             └─ /dev/mtdblock0 を stdio で読み書き
```

libdixim_drm.so の NEEDED は libhermit.so / libgcc_s.so.1 / libc.so.6 のみ。OpenSSL 関数は MD5 と AES 系 5 つのみを import し (ホストプロセスの大域スコープで解決)、AKE の主系ではない (§3.3)。

## 2. モジュールの配布 (majishanzu) と DTCP-IP 版数

DiXiM モジュールは FW イメージに含まれず、ダウンローダ `majishanzu` が DLNA 有効化時に Buffalo の更新サーバから取得して配置する。

- ダウンロードは 2 段: (1) 版数情報ファイルを取得・復号して `new_version` / `url` / `file_body` を得る、(2) 本体を取得・復号して `.deb` 化し `dpkg -i --force-all` で導入する。ホスト名はバイナリにハードコードされている。
- 接続は mTLS で、CA・クライアント証明書・RSA 鍵はバイナリ内蔵の**全機共通**の固定資格情報 (ダウンロード用であり、DTCP デバイス証明書ではない)。試行ごとに一時ファイルへ書き出され、使用後にゼロ上書き + unlink で消去される。
- 版数比較は数値パースなしの `strcmp(cur_version, new_version)` で、cur が無いか辞書順で小さいときだけ更新へ進む。
- 情報ファイルと本体の復号パスワードは、SPI フラッシュの固定レコード (§5 の id0) から得る。majishanzu 内蔵の読み出し層は libhermit にはリンクしておらず、同じレコードを読む静的コードである。
- **DTCP-IP 版数の内訳 (確定)**: 実機 Web UI の表示 `5.2.133-20151113` は、dms_sync の `version` ファイルの `SDK_VERSION=5.2.133` と、状態ファイル `majishanzu_state` の `Version=20151113` (取得した情報ファイルの `new_version` そのもの、`Status=0`) の合成である。実機の画面表示とも一致を確認した。
- SDK 構成 (モジュール内の `linked-dixim-sdks` 記録): dixim-dms 5.2.80、dixim-drm 1.3.27.0_buffalo_nas_tc_26、dixim-dtcp 1.3.27.0_buffalo_nas_tc_26、dixim-pl 5.2.34、dixim-upnp 5.2.42、dixim-upnpa 5.2.78。

解析対象バイナリ:

| ファイル | サイズ | SHA-256 | 備考 |
|---|---|---|---|
| `libdixim_drm.so` | 1,531,852 B | `c5edad6ca70098d2ffac27de50b3cea47813e92800c8a66a5da1cae1a7b4001d` | ARM、stripped (dynsym 265 件)。実機配置は `/usr/local/Digital/buffalo/dms_sync/` |
| `dms_sync` | 4,478,647 B | `218689d37972967914a7264623a2cb448cda20a966813f0eed95c47e206248d6` | DiXiM DMS 本体 (C++)、stripped |
| `libhermit.so.1.0.1` | 26,819 B | `9fd06411571ce544f96716cf67c07309609769b7d67122306a81e5df652c19e9` | **not stripped**。実機 rootfs の `/usr/local/lib/` から採取。Buffalo 独自の鍵金庫ライブラリ |
| `twonkyserver` | 1,945,892 B | `9a0322b86bc2f32784f30ec84bd548e8d424f3203faaa57e42679164c5609970` | TwonkyServer 7.1.1-dsd、stripped (dynsym 336 件) |
| `majishanzu` | 33,264 B | `d1177e75474891b5098f192a7151c6cc90fb5f81a5dbd2fad8c3bac347cbe609` | ダウンローダ、stripped |

手法: llvm-objdump / readelf / nm -D + capstone ベースの注釈付けによる静的逆アセンブル (関数境界は `.ARM.exidx` から復元)。実機 HDD のファイルシステム照合 (ext3 は読み取りマウント、XFS は `xfs_ncheck` / `xfs_db -r` による全 inode 走査) も併用した。

## 3. AKE プロトコル実装

### 3.1 API と駆動

libdixim_drm.so の DTCP エンジン API (`ddtcp_*`、dynsym にエクスポート) の主なもの:

| API | 役割 |
|---|---|
| `ddtcp_create_dtcp` / `ddtcp_startup` / `ddtcp_shutdown` / `ddtcp_destroy_dtcp` | エンジンの生成・開始・終了・破棄。生成時は引数パラメータブロックの整合性ハッシュ (multiply-xor 型) を検証する |
| `ddtcp_set_additional_param` | プラットフォームコールバック (デバイスデータ提供) の登録。種別 1 のみ受理 |
| `ddtcp_source_listen_ake` / `ddtcp_source_listen_ake_3` | ソース側 AKE の listen 開始 |
| `ddtcp_source_listen_ra_ake` | リモートアクセス用 AKE の listen (同一実体に RA フラグで入る) |
| `ddtcp_sink_do_ake` | シンク側 AKE の実行 |
| `ddtcp_sink_mv_do_ake` / `ddtcp_sink_mv_get_kxm_label` | Move 用 AKE と Kxm ラベル取得 |
| `ddtcp_source_expire_kx` | Kx の失効 (§3.5) |
| `ddtcp_set_ecc_timing_back` | ECC 演算のタイミング対策の切替。dms_sync が生成直後に呼ぶ |
| `ddtcp_set_source_connection_timeout` | 接続タイムアウト値のセッタ。**失敗時ログ文字列は "Failed to set listen max ake connection" で実体と文言が一致していない** (DiXiM/Buffalo 側の取り違えとみられる)。同時接続数の設定と読んではいけない |
| `ddtcp_get_device_id_hash` / RSR 系 (§3.7) | 機器 ID ハッシュ (20 バイト) と登録管理 |

dms_sync 側の駆動役は `dixim::dmsp::dtcp::dtcpbridge`:

- 生成時: `ddtcp_create_dtcp` → `ddtcp_set_source_connection_timeout(handle, 1000)` → `ddtcp_set_ecc_timing_back()`。
- monitor スレッド: `ddtcp_set_additional_param(handle, 1, コールバック)` → `ddtcp_startup(handle)` → `ddtcp_source_listen_ake(handle, addr, port, …)` の順に開始し、失敗時は shutdown してリトライする。
- ネットワークインタフェース変化時: `ddtcp_source_expire_kx(handle)` で Kx を失効させる (§3.5)。
- 終了時: listen 停止 → shutdown → destroy。

ポートと広告:

- **AKE ポート: 58293** (サービス設定 `device_conf.xml` のプレースホルダ `[[AKE_PORT]]` の値で、サービス記述の HttpMediaTransport パラメータ `ake_port` に展開される)。
- DMS 本体 (UPnP/HTTP) ポート: **55247**。
- DIDL 側では `DTCP1HOST` / `DTCP1PORT` / `DTCP1RAPORT` のテンプレートで接続先が広告され、コンテンツの MIME は `application/x-dtcp1`、DLNA プロファイルは `DTCP_MPEG_TS_JP_T` 等の DTCP 系。
- この製品はソース (配信) が主機能だが、シンク側 AKE (`ddtcp_sink_do_ake`) も他機からのダウンロード / Move 受けのために使われる (呼出は通常ダウンロード系と転送系の 2 箇所、ログに "DO AKE: host=%s, port=%u" を出す)。

### 3.2 AKE コマンド体系 (全 30 種)

AKE コマンド名の解決関数 (libdixim_drm 内 `0x5eca0`) の分岐表から確定した列挙。受信コマンド値に対して使われるため、この列挙がそのままワイヤ上のコマンド番号とみられる (実通信キャプチャによる裏付けは未実施、§9)。

| 値 | 名前 | 値 | 名前 |
|---|---|---|---|
| 0 | Invalid | 15 | AKE_CANCEL |
| 1 | STATUS | 16 | CAPABILITY_EXCHANGE |
| 2 | CHALLENGE | 17 | MV_INITIATE |
| 3 | RESPONSE | 18 | MV_EXCHANGE_KEY |
| 4 | RESPONSE2 | 19 | MV_CONT_KEY_CONF |
| 5 | RTT_READY | 20 | MV_FINALIZE |
| 6 | RTT_SETUP | 21 | MV_COMPLETE |
| 7 | RTT_TEST | 22 | MV_CANCEL |
| 8 | RTT_VERIFY | 23 | SET_CMI |
| 9 | RTT_BG | 24 | SET_DTCP_MODE |
| 10 | CONT_KEY_CONF | 25 | CMI_REQ |
| 11 | CAPABILITY_REQ | 26 | CONTENT_KEY_REQ2 |
| 12 | EXCHANGE_KEY | 27 | CAPABILITY_REQ2 |
| 13 | SRM | 28 | RA_REGISTER |
| 14 | CONTENT_KEY | 29 | RA_MANAGEMENT |

標準 DTCP AKE の流れ (CHALLENGE → RESPONSE → RESPONSE2 → EXCHANGE_KEY → CONTENT_KEY、確認は CONT_KEY_CONF) に、RTT (Round Trip Time、リモートアクセスの近接検証) 系 5 種、MV (Move) 系 6 種、RA (Remote Access) 系 2 種と、能力交換・CMI・モード設定の拡張が加わった構成である。pydtcpip (docs/32) が Sink 側で実装する手順 (CHALLENGE での証明書提示、相手証明書の DTLA 署名検証と SRM 失効チェック、RESPONSE 署名検証、RTT 応答、EXCHANGE_KEY / MV_EXCHANGE_KEY の受領) は、このコマンド体系の部分集合として対応する。

### 3.3 暗号プリミティブ

静的リンクされた **LibTomCrypt** の構成は、残存するソースパス文字列と記述子テーブルから確定できる:

| 分類 | 含まれるもの | 含まれないもの |
|---|---|---|
| 対称暗号 | AES のみ (記述子 "rijndael") | 他の暗号の記述子なし |
| モード | CBC のみ (cbc_start / cbc_encrypt / cbc_decrypt / cbc_setiv / cbc_done) | ECB/CTR/CFB/OFB のモードファイルは無い → LTC 経由の対称暗号は全て AES-CBC |
| ハッシュ | SHA-1 のみ | SHA-256 等なし |
| ECC | ecc_make_key / ecc_sign_hash / ecc_verify_hash / ltc_ecc_mulmod / ltc_ecc_mul2add 等 | ecc_shared_secret.c は無い → **ECDH は DiXiM 側が ltc_ecc_mulmod を直接使って実装**しているとみられる (推定) |
| その他 | RSA、DER/ASN.1、LibTomMath | — |

- 署名・検証は ECDSA (ecc_sign_hash / ecc_verify_hash)、ハッシュは SHA-1。これは DTCP の Full Authentication の規定 (docs/32) と一致する。
- **cryptodev の併用**: AKE の鍵交換まわり (libdixim_drm 内 `0x4e838`〜`0x50078` の関数群) からは `/dev/crypto` バックエンド (open + CRIOGET / CIOCGSESSION 等の ioctl) が呼ばれる。Kx/Kc に関わる AES 演算の一部はハードウェア支援を受ける経路がある。どの演算が LTC でどれが cryptodev かの完全な切り分けは未確定 (§9)。
- OpenSSL の import (MD5、AES_cbc_encrypt 等) の呼出はトランスコード領域と個体 ID 生成に集中し、AKE / PCP の主系ではない。
- libdixim_drm の ioctl 全 40 箇所を目録化した結果、向け先は /dev/crypto (5)、ソケット (6)、MB86M01 (約 21)、USB (5) で、MTD 向けは 0 件 (§5.2)。

### 3.4 使用曲線について (確定・推定・注記の書き分け)

- **確定**: 鍵寸法は 160 ビット級である。秘密鍵 20 バイト = 160 ビット。証明書 88 バイトは、ヘッダ 8 バイト + 公開鍵 40 バイト (X|Y 各 20) + DTLA 署名 40 バイト (r|s 各 20) と分解でき、160 ビット級でちょうど一致する (192 ビットなら公開鍵・署名とも 48 バイトずつになり 88 バイトに収まらない)。
- **推定 (逆アセンブル資料側)**: LibTomCrypt の曲線テーブルには SECP112R1 / SECP128R1 / SECP160R1 / SECP192R1 / SECP224R1 / SECP256R1 / SECP384R1 / SECP521R1 の 8 種が格納されており、寸法から使用曲線は SECP160R1 と推定された。ただし AKE 実行時にどのエントリが選択されるか、コード上の選択箇所は特定できていない。
- **注記**: pydtcpip (docs/32) が内蔵する曲線は、DTCP 仕様の専用曲線 (公開仕様ではパラメータが省略されている独自曲線、160 ビット級) である。デバイス証明書は DTLA がその曲線上で署名するものであり、実機が他の DTCP 機器と相互運用できる以上、実機の AKE も同一の曲線でなければならない。したがって「SECP160R1」は寸法からの同定ラベルに留め、**実態は DTCP 専用曲線とみるべき**である。両者が同一パラメータか否かは、2026-11-17 に本人が行った実値による署名検証 (§7) が pydtcpip 内蔵の DTLA 公開鍵で通過したことにより実証された (本調査の静的解析時点では未実施だった)。

### 3.5 Kx (交換鍵) の導出と失効

- Kx は EXCHANGE_KEY 手続きで ECDH により共有される (実装は §3.3 の通り mulmod ベースと推定)。共有秘密から Kx への導出の詳細 (ハッシュ適用の有無、ラベル文字列) は未確定。
- 対比: pydtcpip (docs/32) の Sink 側実装では、一時鍵による ECDH の共有秘密の x 座標の下位 96 ビット (12 バイト) を認証鍵とし、交換鍵は認証鍵との XOR で復元される (Move 時は SHA1 由来の別マスク)。DiXiM (ソース側) の内部導出がこれと同一形式かは未確定である。
- 失効: `ddtcp_source_expire_kx` は内部の Kx エントリ列を走査して失効させ、登録済みコールバックで通知する「失効させる側」の API で、期限の絶対値 (秒数) はこの API 内には現れない。生成側の定数までは追跡できておらず、**Kx 有効期限の数値は未確定**。
- 運用: dms_sync はネットワークインタフェースの変化 (IP アドレス変化) のたびに expire_kx を呼び、旧い Kx を失効させる。

### 3.6 Kc (コンテンツ鍵) の生成・配送

- コマンド構成から、標準 DTCP と同様に **Kc はソース側が生成し、Kx で保護して CONTENT_KEY (14) で送り、シンクが CONT_KEY_CONF (10) で確認する**流れを持つことが確定している。CONTENT_KEY_REQ2 (26) という第 2 系統の要求コマンドもある。
- メッセージ内部の暗号化パラメータ (AES-CBC の IV 導出等) の詳細は未確定。
- Move 時は Kxm ラベル (`ddtcp_sink_mv_get_kxm_label`) を使う別系統で、コミットメントは ddrm 側の `ddrm_sink_do_commitment` が担う。

### 3.7 RSR (登録デバイス管理)

- lib 側 API (`ddtcp_source_is_device_registered_in_rsr` 等) の実体は、dtcp 内部オブジェクト上のコンテナ操作のみで、ファイル I/O の呼出は無い。エントリは device_id_hash **20 バイト** (SHA-1 サイズ) の列である。
- **RSR はプロセスメモリ上のリストで、lib レベルでの永続化は無い。** さらに dms_sync は RSR 系 API (および `ddtcp_get_device_id_hash`、`ddtcp_source_listen_ra_ake`) を import していない。この製品では、登録デバイスの照会・削除を DMS 側から行う経路は使われていない。

## 4. コンテンツ暗号化 (PCP) と配信

- 送信側の実体は `ddrm_source_send_data` で、メディアフィルタとして HTTP 送信経路に差し込まれ、データはフィルタ内で PCP 化されてから送られる。暗号は **AES-CBC (LibTomCrypt 実装) によるホスト側ソフトウェア処理**が本命 (同関数から /dev/crypto バックエンドへの直接呼出は無いことを呼出一覧で確認。関数ポインタ経由の間接利用までは否定できないため、その範囲は未確定とする)。
- **MB86M01 への PCP 委譲は無い。** トランスコーダチップ (Fujitsu MB86M01、`/dev/m01fmb0`、FMB_API ioctl 群) はファームウェア読込みとトランスコード制御専用で、DRM/AKE 演算には使われない。チップ自身の SPI ROM 書き込みも SoC 側フラッシュとは別物である。
- DTCP 固有の HTTP ヘッダは lib のユーティリティが処理する: `Content-Range.dtcp.com`、`BLKMove.dtcp.com`、`Alt-ExchangeKey.dtcp.com`、`CMI.dtcp.com`、`RemoteAccess.dtcp.com`。
- **同時 DTCP ストリーム上限は 2** (サービス記述の HttpMediaTransport パラメータ `max_dtcp_stream_count=2`)。Twonky 経路でも、ini のセッション上限はコンパイル時デフォルト "8" を Buffalo の設定が 2 に上書きしており、この製品の DTCP 同時配信上限は両経路とも 2 で揃えられている。lib (ddtcp) 層に公開された同時 AKE 接続数の設定 API は無い。
- 配信可否は cipher_file 機構 (暗号化ファイルの状態・CCI 判定) と連動する。ddrm のソース生成は cipher_file の状態確認を経て行われる。

## 5. 資格情報プロビジョニング

### 5.1 SPI フラッシュ内のレコード表 (確定)

デバイス証明書・秘密鍵の出所は、SoC の SPI フラッシュ `/dev/mtdblock0` である。読み出しは DiXiM 本体ではなく Buffalo 製 **libhermit.so** が担う。レコード表は libhermit の内部関数 (GetKeyPos / getKeyLength / GetDTCPKeyEncLen 等) の即値から確定した:

| id | フラッシュ offset | 平文長 | 暗号文長 | 内容 |
|---|---|---|---|---|
| 0 | `0xC07F0` | 16 B | (平文) | 他レコードの復号パスフレーズ源。復号なしで平文のまま読まれる |
| 1 | `0xC0070` | 20 B | 48 B | 鍵データ (機器秘密鍵相当) |
| 2 | `0xC0000` | **88 B** | 112 B | **デバイス証明書** |
| 3 | `0xC00A0` | 20 B | 48 B | 鍵データ |
| 4 | `0xC00D0` | 最大 64 B | 80 B | SRM データ (長さはデータ依存) |

- 暗号文長は OpenSSL `Salted__` 形式 (8 B magic + 8 B salt + 16 B 倍数の CBC 暗号文) と整合する: 平文 20 → 暗号文 48 (16+32)、平文 88 → 112 (16+96)、平文 64 → 80 (16+64)。いずれも PKCS#7 パディング込みで一致。
- majishanzu が DL モジュールの復号に使うパスワード (§2) は、この表の id0 と同一レコードである。**この領域は Buffalo 製品共通の「鍵金庫」レイアウト**で、majishanzu は id0 しか使わないが、DiXiM は id1〜id4 まで使う。
- 関連する別レコード: ハッシュレコード群 (フラッシュ `0xD0000` 起点・スロット間隔 `0x1000` の 48 バイト暗号文レコードで、復号すると 20 バイトのハッシュになる。`0xDF900` にも 20 バイトの読み書き対象がある) が libhermit に実装され、コールバック種別 6/7 で供給・更新される。DTCP のどの手続きに対応するかは未確定 (§9)。
- 固定データ領域 `0xC04F0` の 16 バイトもコールバック種別 5 で供給される。
- なお libdixim_drm 自身が `/dev/mtdblock0` へ書く箇所 (offset `0xC0800` への 32 バイト) は MB86M01 セキュアトランスコード用の共有鍵管理で、DTCP の証明書経路とは別である。

### 5.2 読み出し手段 (確定)

- libhermit の読み出しは `fopen("/dev/mtdblock0", "rb")` → `fseek` → `fread` のみ。import に ioctl / open / read / lseek は無く、あるのは stdio と OpenSSL BIO/EVP のみ。
- libdixim_drm の ioctl 全 40 箇所も MTD 向けは皆無 (§3.3) で、majishanzu 内蔵層も stdio のみ。
- **結論: 公式 FW が SPI フラッシュを読む手段は、3 コンポーネントとも「/dev/mtdblock0 を通常ファイルとして開く汎用読み取り」であり、MTD キャラクタデバイスの ioctl でも、Buffalo 独自コマンド/プロトコルでもない。** 独自なのはレコードの配置と形式だけである。
- 復号後の作業は RAM ディスク (`/mnt/ram/`) 上の作業ファイル経由で行われ、作業ファイルはゼロ書込み + unlink の安全消去で後始末される。

### 5.3 暗号化形式 (確定) と保護構造 (評価)

- id1〜id4 の復号は `EncryptDecryptFile` が OpenSSL の BIO_f_cipher + EVP_aes_128_cbc で行い、鍵導出は `EVP_BytesToKey(EVP_aes_128_cbc, EVP_md5, salt, pass, passlen, count=1, key, iv)`、先頭 8 バイトが文字列 `Salted__` と照合される。**完全に `openssl enc -aes-128-cbc -md md5` 互換形式**である。
- パスフレーズは `file:` 接頭辞で、id0 の 16 バイトを置いた RAM ファイルが指定される。補助として、id0 の 16 バイトそのものを「共通パスフレーズ」、id1 を復号して得る 20 バイトを「個別パスフレーズ」とする生成関数も存在する (ハッシュレコードの変換は共通パスフレーズを使う)。
- 評価: 証明書・秘密鍵はフラッシュ上で暗号化保管されているが、そのパスフレーズ源 (id0) が**同一フラッシュ内に平文で存在する**ため、鍵の保護は実質的に「フラッシュを読み出せるかどうか」に帰着する構造である。これは設計の是非ではなく観測された構造の記述である。

### 5.4 AKE エンジンへの供給経路 (確定)

libdixim_drm 内のプラットフォームコールバックが種別で分岐してデバイスデータを提供する:

| 種別 | 内容 |
|---|---|
| 1 | **デバイスデータ一式 128 バイト** = id2 の 88 B + id1 の 20 B + id3 の 20 B を長さで連結 |
| 2 | SRM データ (id4) |
| 3 | セキュリティ鍵 16 バイト (id0) |
| 4 | 4 バイト big-endian の整数値 1 |
| 5 | フラッシュ `0xC04F0` の固定 16 バイト |
| 6 | ハッシュ 20 バイト (スロット 1/2) |
| 7 | フラッシュ `0xDF900` の生ハッシュ 20 バイト |

- 書き込み側もあり、種別 2 は SRM の書戻し (id4 の再暗号化)、種別 6/7 はハッシュレコードの更新に対応する。SRM の更新保存先もこのフラッシュである。
- デバイスデータは呼出側 (dms_sync) からは渡されず、**エンジンがコールバック経由で libhermit に取りに行く**設計である。
- libdixim_drm.so 内にデバイス証明書の埋め込みは無い (証明書は個体別でフラッシュ側にある、という上記フローと整合)。
- 付記: libhermit のエクスポート名は曜日・月名 (June / July / March 等) に難読化されており、July = レコード復号取得、March = 平文長取得、May = 定数 16、Sunday = 定数 20、Monday/Tuesday = ハッシュ読み出し/更新、Friday/Saturday = `0xDF900` の読み/書き、October = SRM 書戻し、に対応する (libhermit が not stripped のため内部関数名から対応が確定できた)。

## 6. torne 側プロビジョニングとの対比

本リポジトリで調査してきた torne mobile (Sink 側アプリ) の資格情報供給 (docs/33〜36、docs/45) と対比する。どちらも「資格情報は初期化 API の引数では渡らない」という設計は共通するが、一次所在と保護の形は大きく異なる。

| 観点 | torne mobile (docs/33〜36、45) | LS210D (本書) |
|---|---|---|
| 役割 | Sink (クライアントアプリ) | Source (NAS サーバ。Sink 機能も併有) |
| DTCP スタック | Sony 製ミドルウェア DEWEY (アプリ内蔵)。AKE 暗号は DEWEY のみに存在 | DiXiM SDK (dixim-dtcp) + Buffalo 製 libhermit |
| 資格情報の一次所在 | サーバ (GAE) から配布される暗号化資産ファイル `PvrAssetData.cxml` | SPI フラッシュ内のレコード表 (工場プロビジョニング) |
| 保護の束縛 | 資産ファイルの復号には同一インスタンスの 3 点セット (cxml + mobileId + キーチェーン UUID) が必要で、鍵はインスタンス固有値から導出される | パスフレーズ源 (id0) が同一フラッシュ内に平文。保護はフラッシュ読み出し可否に帰着 (§5.3) |
| 供給経路 | DAL アイテムストア (証明書 = アイテム #9、組立て相手 = アイテム #13)。第 2 供給路は提供オブジェクトの登録 (証明書用/鍵用) | コールバック種別 1 で 128 バイト一括供給。エンジンが libhermit へ取りに行く |
| 証明書の形式 | 証明書設定関数は 88 / 132 バイトを受理し、バイト 3〜7 = デバイス ID を難読化保持 | 88 バイト (baseline)。バイト 3〜7 = デバイス ID は pydtcpip の読み取り位置とも一致 (§7) |
| SRM の置き場 | DEWEY 側の管理 (詳細は未確定) | フラッシュ id4 に保持し、更新は再暗号化して書戻し |
| 残る未確定の所在 | LAN 再生時に誰が DEWEY の AKE を駆動するかが未同定 (docs/45) | AKE 駆動は dtcpbridge で同定済み。残る未確定は暗号内部 (Kx 導出・曲線選択箇所) |

## 7. pydtcpip の DeviceCredentials 検証との整合性 (評価と実証)

pydtcpip の `DeviceCredentials` は構築時に次の検証を行う (docs/32 §3.2):

1. 証明書が 88 バイトの baseline 証明書 (先頭バイト = 種別 1、SRM 世代上限の検査を含む) で、先頭 48 バイトに対する末尾 40 バイトの DTLA 署名 (ECDSA-SHA1) が、コード内蔵の DTLA 公開鍵で検証できること。
2. 秘密鍵が 20 バイトで、そこから導いた公開鍵が証明書の公開鍵 (8〜48 バイト) と一致すること。機器 ID は証明書の 3〜8 バイトから読まれる。

LS210D の資格情報がこの検証に対してどう位置づくか。当初は構造と検証コードからの評価だったが、2026-11-17 に本人が実値による検証を手動で実施して成功し、評価は実証へ格上げされた (鍵の値は従来通り記録しない):

- **形式 (整合)**: レコードの平文長 (証明書 88 バイト、鍵 20 バイト) は検証の想定寸法と一致する。証明書の内部分解 (ヘッダ 8 + 公開鍵 40 + 署名 40) も §3.4 の通り検証側の読み取り位置と整合する。
- **DTLA 署名 (実証済み)**: 証明書は DTLA ライセンス製品の工場プロビジョニング品である。本人が 2026-11-17 に実施した `DeviceCredentials` 検証で、コード内蔵の DTLA 公開鍵による署名検証を通過した。これにより、実機証明書が pydtcpip 内蔵の DTCP 専用曲線上で署名されていることも実証された (§3.4)。
- **ペア対応 (実証で確定)**: AKE へ供給される 20 バイトレコードは 2 つ (id1 / id3) ある。静的解析の時点ではどちらが証明書 (id2) のペアか未確定だったが、本人の検証では秘密鍵から導いた公開鍵が証明書の公開鍵と一致し、ペアである側が実証をもって確定した。他方の 20 バイトの役割 (個別パスフレーズ源としての id1 の使われ方 §5.3 との関係を含む) は未確定のまま。
- **SRM (実走で障害なし)**: id4 の SRM データ自体の内部形式は未確定 (§9) だが、同一ペアによる実機 nasne との AKE 実走 (docs/48・49) が完走しており、その範囲では pydtcpip 側の SRM 失効チェック (相手・自分の双方の証明書を検査) が障害になることはなかった。

**実証の記録 (2026-11-17)**: 本調査 (静的解析) の時点では実値を取り出していないため実証は行っていなかったが、その後、本人が LS210D の資格情報ペアに対して pydtcpip の `DeviceCredentials` 検証を手動で実施し、**成功した** (DTLA 署名検証・秘密鍵のスカラー範囲・導出公開鍵と証明書の公開鍵の一致、の全条件を通過)。さらに同日、同一ペアを用いた救出パイプライン (docs/48・49) が実機 nasne との AKE 完走と録画取得まで成功しており、検証だけでなく AKE の実運用でもペアが機能することが実証されている。したがって本節の当初の評価 (「検証の関門はすべて、正規品の資格情報であれば構造的に通るもの」) は実証済みに格上げされる。鍵の値は従来通り記録しない。

意義の整理: nasne / torne 側では「正規ペアの実在形式」が長く未確定だったが、市販ソース製品では、資格情報は「フラッシュ内レコード表 + 汎用 stdio 読み出し + openssl enc 互換形式」という平明な形で実装されていた。プロビジョニングの設計はメーカー・製品で大きく異なる (torne のサーバ配布・インスタンス束縛型との対比が §6) 一方、証明書形式と AKE は DTCP 仕様で共通であり、片側の知見がもう片側の物差しになる。

## 8. 実機で確認した事項

- 公式 FW 稼働中の実機で、FW 内蔵の sshd による root ログインが可能だった (調査用の実験ディスク構成での確認)。
- 実機の `/proc/mtd` は mtd0 単一区画 `spi_flash`、サイズ 1 MiB、erasesize 64 KiB。レコード表の offset (0xC0000 台) はこの範囲内にある。
- SPI フラッシュ全域のバックアップを読み取りのみで取得済み。2 回読みの SHA-256 が一致した (SHA-256: `25ed14bdae1d01c269621b01e8807a25e310d997ffd121a92ac1e595b660417a`)。内容の構造として、前半に U-Boot 2011.12 (Marvell 版) があり、0xC0000 のブロックに疎なデータ (レコード表) の実在を確認した (レコードの値は読んでいない)。
- 実機 HDD の照合: rootfs (FW 1.86) に dms_sync ツリーが実在し、`twonky-alt` は存在しなかった。データ領域 (XFS) の全 inode 走査で `.hierophant` / `.midbeans` (Twonky モードで dtcp_disk 直下へコピーされる隠しディレクトリの候補だったもの) は存在せず、Twonky モード専物と判断した。DiXiM のデータ側作業領域はデータ領域の `.condition/conf/dms/` (DB 群 + private_data_home) で、private_data_home の `nmcc.db` は reg テーブル 0 行であり、証明書の置き場ではない。
- 実機 Web UI のフッターに表示される DTCP-IP 版数 `5.2.133-20151113` が §2 の内訳と一致した。
- 2026-11-17、本人が LS210D の資格情報ペアに pydtcpip の `DeviceCredentials` 検証を手動で実施し、成功した (§7)。同日、同一ペアを用いた救出パイプラインが実機 nasne との AKE 完走・録画取得にも成功している (docs/48・49)。鍵の値は記録していない。

## 9. 未確定事項

1. **使用 ECC 曲線のコード上の選択箇所**: 寸法からは 160 ビット級で確定。実機証明書と pydtcpip 内蔵曲線のパラメータ一致は §7 の実証で確定した。残る未確定は、AKE 実行時に libdixim_drm の曲線テーブルのどのエントリが選ばれるかというコード上の選択箇所のみで、特定できていない (SECP160R1 という同定ラベル自体は §3.4 の注記の通り、寸法からの推定に留まる)。
2. **AKE コマンド番号とワイヤ形式の対応**: 列挙 (§3.2) は名前解決関数の分岐表由来で、実通信キャプチャによる裏付けは無い。
3. **Kx 導出の詳細と有効期限の数値**: ECDH 後のハッシュ適用・ラベル、期限秒数は未特定。expire_kx が失効処理 API であること、NIC 変化で呼ばれることは確定。
4. **Kc 配送形式の詳細**: CONTENT_KEY コマンドの存在と役割は確定。Kx での暗号化形式 (IV 導出等) は未特定。
5. **cryptodev の担当範囲**: AKE 鍵交換まわりから /dev/crypto が呼ばれることは確定。どの演算が LTC でどれが cryptodev か、PCP 本体に間接的に使われるかは未確定。
6. **id1 / id3 のうちペアでない側の役割**: ペア対応は §7 の実証で確定した。ペアでない側の 20 バイトレコードの役割は未確定のまま。
7. **SRM データ (id4) の内部形式**: 長さがデータ依存 (暗号文 80 バイト → 平文最大 64 バイト) であることまで。
8. **ハッシュレコード (0xD0000〜、0xDF900) の意味付け**: 48 バイト暗号文 ⇔ 20 バイトハッシュの読み書き機構と、コールバック種別 6/7 での供給は確定したが、DTCP のどの手続き (RA 登録管理か Move のコミットメントか) に対応するかは未確定。
9. **libdixim_drm 内の大きな混合関数の正体**: 定数と multiply-xor バイトループを持ち、create_dtcp 冒頭のパラメータ整合性検証と同型。device_id_hash 生成か Kx 混合の一部かは未同定。
10. **lib 内の uint16 フィールド対の意味**: 0x400 を上限とする内部セッタ群があるが、dms_sync からの呼出は確認できず、何の上限かは未確定。同時 AKE 接続数の上限とは確定していない。

## 付録: 主要関数アドレス

libdixim_drm.so:

| アドレス | 名前 / 役割 |
|---|---|
| `0x522fc` | ddtcp_create_dtcp (パラメータ整合性検証付き) |
| `0x1fb04` | ddtcp_sink_do_ake |
| `0x2e4ec` / `0x2e430` / `0x2e3b0` | ddtcp_source_listen_ake / _ake_3 / _ra_ake |
| `0x3cc18` | ddtcp_source_expire_kx |
| `0x3cd08` / `0x3cd20` / `0x3cd38` | RSR 照会 / 削除 / ハッシュ配列取得 |
| `0x5964c` | ddtcp_get_device_id_hash |
| `0x59000` | ddtcp_set_additional_param (種別 1 のみ受理) |
| `0x594e4` | ddtcp_set_source_connection_timeout |
| `0x59230` | ddtcp_set_ecc_timing_back |
| `0x5eca0` | AKE コマンド名解決 (列挙の出所) |
| `0x784d0` | デバイスデータ提供コールバック (種別 1〜7) |
| `0x787d4` | デバイスデータ書込みディスパッチャ |
| `0x102e0` | ddrm_source_send_data (PCP 送信) |
| `0x65850` 群 | /dev/crypto (cryptodev) バックエンド |

libhermit.so.1.0.1:

| アドレス | 名前 |
|---|---|
| `0x11c4` / `0x1284` / `0x27e8` / `0x2bc4` | GetKeyPos / GetKeyName / getKeyLength / GetDTCPKeyEncLen |
| `0x15fc` | GetSecurityKey (id0 平文読み) |
| `0x19bc` / `0x1a2c` | OpenSecKey (fopen "rb") / OpenSecKey_write (fopen "wb+") |
| `0x13f8` | ReadKey (fseek + fread) |
| `0x28ec` / `0x2c5c` | getKey / GetDTCPIPKeys |
| `0x49c4` | EncryptDecryptFile (EVP_aes_128_cbc + EVP_BytesToKey、count=1) |
| `0x4640` / `0x46bc` | generateCommonPassphrase / generateIndividualPassphrase |

dms_sync:

| アドレス | 名前 / 役割 |
|---|---|
| `0xbb288` | dtcpbridge 生成 (create_dtcp + set_source_connection_timeout(handle, 1000) + set_ecc_timing_back) |
| `0xbbe40` | dtcpbridge::monitor (set_additional_param → startup → source_listen_ake) |
| `0xbb9f4` 付近 | netif_change_handler (expire_kx 呼出) |
