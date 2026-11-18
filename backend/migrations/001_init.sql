-- FLASH の最初の形。
--
-- **利用者のデータを持つ表には、必ず user_id と行レベルセキュリティ（RLS）を付ける。**
-- 新しい表を足すときは、この下の「RLS をかける」の段落を写して同じことをする。
-- 付け忘れると、その表だけ「鍵の無いロッカー」になる。
-- （tests/test_rls.py が、user_id を持つのに RLS が無い表を見つけたら落ちる）
--
-- 実行するのは表の持ち主 flash_owner。アプリは flash_app で繋ぐ。
-- 表の持ち主は RLS をすり抜ける。だから **アプリは持ち主ではない役割で繋ぐ**
-- ことで RLS を効かせている（config.py の2本の接続）。

-- 「今だれの操作か」。アプリが取引ごとに set_config('app.user_id', ...) で入れる。
-- 入っていなければ NULL → どの行の user_id とも一致しない → 何も見えない（閉じる側に倒れる）。
CREATE OR REPLACE FUNCTION flash_current_user() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.user_id', true), '')::uuid
$$;

-- ---- 利用者 ---------------------------------------------------------------
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL UNIQUE,
  name          text,
  google_sub    text UNIQUE,              -- Google 側の不変の ID。メールは変わりうる
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz
);

-- ---- 外部とのつなぎ（いまは Canvas のカレンダーフィードだけ） ---------------------
--
-- secret_enc は **暗号化した URL**。平文はどこにも書かない。
-- 本人が「切る」を押したら行ごと消す（＝FLASH の手元に鍵が残らない）。
CREATE TABLE connections (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('canvas_feed')),
  secret_enc    text NOT NULL,
  hint          text,                      -- 画面に出す目印（URL の末尾数文字など）。秘密ではない
  status        text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'ok', 'error')),
  last_try_at   timestamptz,
  last_ok_at    timestamptz,
  last_error    text,
  last_counts   jsonb,                     -- 前回の取り込みで何が起きたか（件数）
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, kind)
);

-- ---- 科目 ---------------------------------------------------------------
--
-- フィードの「課題名 [コース名]」の [ ] の中身から作る。
-- 日大のコース名は曜日・時限を持っているので、JARVIS と同じ分解で時間割の種になる。
-- display_name / hidden は **本人が決める値**。取り込みでは上書きしない。
CREATE TABLE courses (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source        text NOT NULL DEFAULT 'canvas',
  ext_key       text NOT NULL,             -- フィード上のコース名（そのまま）
  name          text NOT NULL,             -- 分解した科目名
  teacher       text,
  term          text,
  day_of_week   smallint,                  -- 0=月 … 6=日
  period        smallint,
  slot          text,                      -- 「火5」「月1・月2」
  display_name  text,                      -- 本人がつけた呼び名（空なら name）
  hidden        boolean NOT NULL DEFAULT false,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, source, ext_key)
);

-- ---- 課題・予定 ------------------------------------------------------------
--
-- フィードは「未来の全部と、過去30日」しか出さない。だから
--   * 30日より前のものがフィードから消えた → 期間外に出ただけ。残す（履歴）
--   * 期間内のものが消えた → Canvas で削除・非公開にされた。gone_at を付ける
-- 締切が動いたら prev_due_at に前の値を残す（「いつ変わったか」が後で効く）。
--
-- done_at は **本人の印**。フィードには提出状況が載らないので、
-- 「出した」は本人が押す。取り込みでは絶対に触らない。
CREATE TABLE items (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source         text NOT NULL DEFAULT 'canvas',
  ext_uid        text NOT NULL,            -- フィードの UID
  kind           text NOT NULL CHECK (kind IN ('assignment', 'event')),
  title          text NOT NULL,
  course_id      uuid REFERENCES courses(id) ON DELETE SET NULL,
  due_at         timestamptz,
  all_day        boolean NOT NULL DEFAULT false,
  url            text,
  description    text,
  prev_due_at    timestamptz,
  due_changed_at timestamptz,
  first_seen_at  timestamptz NOT NULL DEFAULT now(),
  last_seen_at   timestamptz NOT NULL DEFAULT now(),
  gone_at        timestamptz,
  done_at        timestamptz,
  UNIQUE (user_id, source, ext_uid)
);
CREATE INDEX items_user_due ON items (user_id, due_at);

-- ---- RLS をかける ----------------------------------------------------------
--
-- 「ロッカー自体が本人の鍵でしか開かない」部分。
-- アプリのコードが WHERE user_id = ... を書き忘れても、DB が他人の行を返さない。
-- WITH CHECK は「他人の名義で書き込む」のも止める。
ALTER TABLE users       ENABLE ROW LEVEL SECURITY;
ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE courses     ENABLE ROW LEVEL SECURITY;
ALTER TABLE items       ENABLE ROW LEVEL SECURITY;

CREATE POLICY own_row  ON users       USING (id = flash_current_user()) WITH CHECK (id = flash_current_user());
CREATE POLICY own_rows ON connections USING (user_id = flash_current_user()) WITH CHECK (user_id = flash_current_user());
CREATE POLICY own_rows ON courses     USING (user_id = flash_current_user()) WITH CHECK (user_id = flash_current_user());
CREATE POLICY own_rows ON items       USING (user_id = flash_current_user()) WITH CHECK (user_id = flash_current_user());

-- アプリの役割にできることを絞る。users は「自分の行を読む・名前を直す」だけ。
-- 作るのはログイン処理（SYSTEM 接続）の仕事。
GRANT SELECT, UPDATE (name) ON users TO flash_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON connections, courses, items TO flash_app;
GRANT EXECUTE ON FUNCTION flash_current_user() TO flash_app;
