-- 手元の PostgreSQL（docker compose）を最初に作るときに1回だけ流れる。
--
-- 役割を2つ作る:
--   flash_owner … 表の持ち主。移行（python -m app.migrate）とログイン処理が使う。RLS をすり抜ける
--   flash_app   … アプリが普段使う。RLS が効く。持ち主ではないので、他人の行は DB が隠す
--
-- パスワードは手元専用の仮のもの。本番では必ず別のものにする。
CREATE ROLE flash_owner LOGIN PASSWORD 'flash_owner';
CREATE ROLE flash_app   LOGIN PASSWORD 'flash_app';

CREATE DATABASE flash OWNER flash_owner;
CREATE DATABASE flash_test OWNER flash_owner;   -- pytest 用。テストのたびに中身を作り直す

\connect flash
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO flash_app;
ALTER SCHEMA public OWNER TO flash_owner;

\connect flash_test
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO flash_app;
ALTER SCHEMA public OWNER TO flash_owner;
