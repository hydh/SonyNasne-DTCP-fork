# 38. torne mobile 実機セッション (iPhone SE): 資産フローの発火条件とキーチェーン項目の実在確認

## 1. 位置づけ

- docs/33〜36 の静的解析で、資格情報の 3 点セット (`PvrAssetData.cxml`、mobileId、キーチェーン UUID) が揃えば資産ファイルを復号できる水準に達した。本書は実機で初期化を発火させて収穫を試みた記録である。
- 値そのもの (UUID、DUID 等) は本書に書かない。書くのは存在・属性・タイミング等の観測事実のみ。

## 2. 環境と実施内容 (事実)

- 端末: 脱獄済み iPhone SE (第 1 世代、iOS 15.8)。torne mobile を App Store から導入し、視聴機能の購入を復元した。
- 機体: 公式ファームウェア稼働中の nasne (同一 LAN)。公式 FW で新規録画 (DR / 3 倍) を 1 件行った。
- 実施した操作: nasne とのペアリング、TV ライブ視聴、録画番組の再生、ペアリングの更新。各操作の後にアプリコンテナをファイルシステムから直接取得し、ファイルの増減を差分で確認した。

## 3. 結果

### 3.1 資産ファイルは発火しなかった (事実・否定結果)

- 全操作を通じて **`PvrAssetData.cxml` / `PvrBGMData.cxml` は生成されなかった** (コンテナ差分で確認)。
- ライブ視聴・録画番組の再生・ペアリング更新のいずれも、docs/35 のライセンスフロー (GAE へのレシート送信系) のトリガーではなかった。発火条件は引き続き未確定で、候補は購入・復元まわりの画面遷移や、常駐側プロセス (PvrBgApp) の起動経路など。

### 3.2 キーチェーン項目の実在確認 (事実)

- frida + objection で torne のプロセス内から `ios keychain dump` を実行し、docs/36 で同定したストレージ項目の **実在を確認した**。
  - 作成タイミングはアプリ初回起動時。属性は `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` (docs/36 の静的読みと一致)。
  - 値は文字列ではなく **生の 16 バイト** だった (objection の画面表示では Data 欄が空になり、JSON 出力の dataHex で取得できた)。
  - **docs/36 への訂正候補**: 実機の登録は service = `torne moible`、account = `com.playstation.tornemobile.storage` の向きだった。docs/36 の静的読み (service / account の割り当て) と逆であり、どちらが正かは項目作成コードの再読で要確認。
- あわせて存在を確認した項目 (存在と属性のみ):
  - SNEI / NP 系のデバイス DUID 項目 (`WhenUnlockedThisDeviceOnly`、torne の項目より 32 秒前に作成)。
  - Telepathy の identifierForVendor 項目。
- スタンドアロン版 keychain_dumper (ldid 署名、keychain-access-groups = `*` 等の entitlement 付き) は、この端末では項目が実在するにもかかわらず 0 件しか返さなかった。アプリ文脈で問い合わせる objection では見えたため、これは道具側の限界と判定した。

### 3.3 SHA-256 フックの否定結果 (事実)

- frida で torneplus の CommonCrypto SHA-256 (one-shot `CC_SHA256` と streaming の Update/Final) を記録し、起動 + 視聴操作を行った。
- one-shot は 0 回、streaming の Final は 106 回 (入力総長は 5 バイト × 103、0 バイト × 3)。**64 バイト入力 (G 導出の形) は 0 件** だった。
- G の導出は CommonCrypto の CC_SHA256 経由ではない (自前実装か別プロセスかは未確定)。

### 3.4 TP/device の実物 (事実)

- 初回起動時に `Library/Application Support/TP/device/` へ次が生成された: `TpFlash0.bin` / `TpFlash1.bin` (各 3,328 バイト)、`TpStorage000.bin` (131,072 バイト)、`TpStorage100.bin` (262,144 バイト)、`TpData0.bin` (80 バイト)、`TpLog0_Store.bin.l` (0 バイト)。ペアリング後に `TpLog0_Store.bin` が追加された。
- 中身は非ゼロ率約 99.6% で、暗号化された見た目をしている。
- これは Telepathy (外出先視聴) 側の永続ストレージであり、DTCP-IP の資格情報とは別系統 (docs/21)。命名は Tp + 役割 (Flash / Storage / Data / Log) + バンク番号で、組み込み向け基盤のフラッシュ構成をファイルでエミュレートしたものと解釈する。

### 3.5 視聴機能そのものの動作 (事実)

- ペアリング、TV ライブ視聴、録画番組の再生はいずれも正常に動作した。資格情報の初期化が走らなくても、視聴系の操作は成立している。

## 4. 未確定

- 資産フロー (ライセンス取得) の発火条件。
- mobileId の取得 (発行タイミングと永続化形態は docs/36 以来未確定のまま)。
- G 導出の実装経路 (3.3 の否定結果により CommonCrypto 説は外れた)。
- docs/36 の service / account 割り当ての訂正要否 (3.2)。

## 5. 関連

- 同セッションでの pydtcpip 実機検証は docs/37。機体側の経緯 (書き戻し経路の交代等) は開発側のセッション記録に残した。
