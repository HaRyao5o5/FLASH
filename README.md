# ⚡ FLASH

**F**ucking **L**egendary **A**ssistant **S**ystem **H**ub。

[JARVIS](https://github.com/HaRyao5o5/JARVIS) の考え方を、**友達（同じ大学の学生）も使える形**で作り直したもの。
JARVIS は「自分の部屋」、FLASH は「寮」。

- 玄関の**共用掲示板**：学事日程・シラバス・休講など、全員に同じもの（これから）
- 各自の**鍵付きロッカー**：課題・予定・メモなど、本人しか開けられないもの

## 大事にしていること

1. **預からない。** 大学のパスワードも Canvas のアクセストークンも持たない。
   ログインは Google に「日大の学生か」を確かめてもらうだけ。
2. **他人のロッカーは開かない。** PostgreSQL の行レベルセキュリティ（RLS）で、
   アプリのコードが間違っても DB 自身が他人の行を返さない。`tests/test_rls.py` がそれを見張る。
3. **管理するのは本人。** つなぐ・切る・隠す・「出した」の印は、全部本人が自分のぶんにだけできる。
   サイトの管理者は場所を用意するだけ。

## いまできること（第1段階: Canvas）

- Canvas の**カレンダーフィード**の URL を貼ると、課題の締切と予定が並ぶ
- 30分ごとに自動で取り込み直す。締切が変わったら「締切変更」、Canvas から消えたら「消えたもの」に出る
- 「出した」を本人がチェック（フィードには提出状況が載らないため）
- コース名から科目・担当者・曜日時限を自動で読む（JARVIS の分解をそのまま移植）
- 科目に呼び名をつける・隠す

### JARVIS と違って、フィードでは取れないもの

提出したか・点数・お知らせ・資料・To Do・30日より前の過去。
これは **Canvas のルール上、他人にトークンを発行させて預かることができない**ため
（複数人で使うアプリは、大学が出す開発者キーで OAuth を使うことになっている）。

## 構成

```
FLASH/
├── backend/            FastAPI（Python）
│   ├── app/
│   │   ├── main.py          入口。中間処理・画面の配信・定期取り込み
│   │   ├── config.py        設定（.env）
│   │   ├── db.py            DB への入口。「誰の操作か」を DB に名乗る
│   │   ├── auth.py          ログイン（Google / 開発用）
│   │   ├── canvas_feed.py   フィードの検査・取得・解析・コース名の分解
│   │   ├── sync.py          取り込み（消えた課題・締切変更の判定）
│   │   ├── routes_canvas.py Canvas まわりの API
│   │   ├── crypto.py        URL の暗号化
│   │   └── migrate.py       DB の形を最新にする
│   ├── migrations/     SQL（番号順に流す。流したものは書き換えない）
│   └── tests/          本物の PostgreSQL で動かすテスト
├── frontend/           React + TypeScript（Vite）
└── docker-compose.yml  手元の PostgreSQL
```

## 手元で動かす（Windows / PowerShell）

### 0. 用意するもの

- Python 3.12 以上、Node.js 20 以上
- PostgreSQL。いちばん楽なのは **Docker Desktop**（`docker compose up -d` で立つ）

### 1. DB を立てる

```powershell
docker compose up -d
```

初回だけ `docker/init-roles.sql` が流れて、役割（`flash_owner` / `flash_app`）と DB（`flash` / `flash_test`）ができる。

### 2. サーバー

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

python -m app.tools.make_key --write   # .env を作って、鍵を2本書き込む
python -m app.migrate             # 表を作る
python -m pytest                  # 28 件通れば OK（他人のデータが見えないことも確かめている）

uvicorn app.main:app --reload --port 8000
```

### 3. 画面（別の PowerShell で）

```powershell
cd frontend
npm install
npm run dev
```

http://localhost:5173 を開く。手元では**開発用ログイン**（メールを打つだけ）で入れる。

### 4. 自分の Canvas で試す

Canvas → カレンダー → 右側の「カレンダーフィード」→ URL をコピー → FLASH の「つなぐ」に貼る。

## これから

- [ ] Google ログインの設定（Google Cloud でクライアントを作る。権限は名前とメールだけ）
- [ ] 本番に置く（Fly.io ＋ PostgreSQL の置き場所を決める）
- [ ] PWA（ホーム画面に置く）・通知
- [ ] 共用掲示板: 学事日程・シラバス・教室（JARVIS から移植）
- [ ] 時間割ページ（コース名から読んだ曜日時限で）
