# SonyNasne-DTCP

SIE(旧SCE)製ネットワークレコーダー **nasne CECH-ZNR2J** の **録画保護(DTCP-IP と、HDD への保存時にかかる暗号化)** に関する解析記録を蓄積するリポジトリです。

姉妹プロジェクト [SonyNasne-debian](https://github.com/mar1mo-41414/SonyNasne-debian)(nasne で Debian を動かすための解析とツール)から、録画保護まわりの調査だけを切り出して、こちらに集めます。

## 目的

公式ファームウェアで録画した既存録画(`.dat`)が、

- どのような暗号化で保存されているか
- 鍵がどこで・どう決まり、どこにも平文で存在しないのか
- 再生時に、どの経路で復号され、平文がどこに現れるか

を、静的解析(バイナリ・ドライバ・ファームウェアの解析)と実機観測で確定していくこと。

**鍵の値そのものは書きません**(存在・形式・所在・導出手順の構造まで)。個体を特定できる値(MAC アドレス、機器 ID の実値、HDD のシリアル等)も書きません。

## 分かっていること

- 録画保存の実形態は **SECUREDTS による復号 + GENERIC-AES セッション(モード `0x4000`)による暗号化**。実効鍵は、ホストが渡す control word をファームウェアが内部状態で解決したもので、**鍵そのものはホスト側のどこにも存在しない**([docs/02](docs/02_dat_encryption_model.md))
- DTCP-IP 配信(通常再生)はチップ内閉域で、平文 TS はホストに出ない。一方、リモート視聴(Tp)経路は平文 TS がホストメモリにステージされる設計([docs/03](docs/03_playback_path_and_oracle.md))
- 「復号に必要な鍵だけ実機から抜いて PC で復号する」形は、鍵がホストに存在しない設計のため成立しない。判定の根拠と残る未確定事項は [docs/04](docs/04_open_questions.md) にある
- `.dat` 側の解析(実機チップを復号オラクルとして使う方式を含む)の記録は docs/02〜04 が正本
- 既存録画の取り出しには **DTCP-IP 経由の経路**が使える。正規の資格情報ペアを用意すれば、公式 FW の録画を AKE 経由で復号済み TS として取得できる(DR 録画・3倍録画のどちらも対象)。ツールは [tools/dtcpip-rescue](tools/dtcpip-rescue/)、記録は [docs/48](docs/48_dtcpip_rescue_pipeline.md)・[docs/49](docs/49_dtcpip_rescue_tool_and_windows.md)

## ドキュメント

| 文書 | 内容 |
|---|---|
| [docs/README](docs/README.md) | **索引**(各文書の概要と状態) |
| [01_dtcp_firmware_analysis](docs/01_dtcp_firmware_analysis.md) | DTCP 実装の静的解析(AKE の所在、鍵アンラップ専用モジュール `tpkeydec.ko` の全解読、鍵素材の所在まとめ) |
| [02_dat_encryption_model](docs/02_dat_encryption_model.md) | `.dat` の暗号化モデルと鍵の行方(層構造、保存時の実形態、CW トークン、OTP 読み出しと CW 総当たりの実測) |
| [03_playback_path_and_oracle](docs/03_playback_path_and_oracle.md) | 再生経路と復号オラクル(Tp 経路の平文ステージング、実験 E1〜E4 の設計と E3 の実測) |
| [04_open_questions](docs/04_open_questions.md) | 未確定事項と問いの棚卸し(本丸の問い、オラクル側の問い、副線の方針) |

## 謝辞

DTCP-IP 救出経路は、tsukumijima 氏の [pydtcpip](https://github.com/tsukumijima/pydtcpip) の実装と知見の上に成り立っています。[docs/32](docs/32_pydtcpip_survey.md) での評価と [docs/37](docs/37_pydtcpip_live_verification.md) での実機検証を経て、救出パイプライン ([docs/48](docs/48_dtcpip_rescue_pipeline.md)・[docs/49](docs/49_dtcpip_rescue_tool_and_windows.md)) の AKE と復号は pydtcpip をエンジンとして動いています。pydtcpip が公開されていなければ、この経路には到達できませんでした。深く感謝します。

## 対象・注意

- 対象は、**自分で所有する実機と、自分で録画した録画のみ**です。
- Sony のファームウェア本体、バイナリ、SPI フラッシュの内容は含まれません。解析対象の入手は各自の実機・公開ソースから。
- 派生ツールは tools/ に収録します(現在は DTCP-IP 救出ツール [tools/dtcpip-rescue](tools/dtcpip-rescue/))。
- nasne、PlayStation、B-CAS 等は各社の商標です。本プロジェクトは SIE、各社とは無関係です。

## 支援について

SonyNasne-DTCP は個人の趣味で開発しているフリーソフトです。
もし「応援したい」と思っていただけたら、PayPay で寄付を受け付けています。

- PayPay ID: markunr_m

特典などは特に出せませんし、寄付の有無で機能や対応に差がつくこともありません。
開発の励みになりますので、気が向いたらどうぞ。
