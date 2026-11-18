import { useCallback, useEffect, useState } from "react";
import { api, type CanvasStatus } from "../api";
import { ago } from "../time";
import { summary } from "./Home";

// Canvas をつなぐ・切るページ。
//
// 「FLASH を管理するのは本人」の入口。何を預かっていて、何を預かっていないかを
// ここで正直に見せる。切れば、預けていた URL は FLASH から消える。
export default function Connect() {
  const [st, setSt] = useState<CanvasStatus | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [purge, setPurge] = useState(false);
  const [confirmCut, setConfirmCut] = useState(false);

  const load = useCallback(async () => setSt(await api.get<CanvasStatus>("/api/canvas")), []);
  useEffect(() => {
    load();
  }, [load]);

  const connect = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.put<CanvasStatus>("/api/canvas", { feed_url: url });
      setUrl("");
      setSt(r);
      const c = r.counts;
      setMsg(c ? `つながりました。${c.total}件読み、${c.courses_new}科目を見つけました` : "つながりました");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const syncNow = async () => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.post<CanvasStatus>("/api/canvas/sync");
      setSt(r);
      if (r.counts) setMsg(summary(r.counts.new, r.counts.due_changed, r.counts.gone));
    } catch (e) {
      setErr((e as Error).message);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const cut = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.del(`/api/canvas${purge ? "?purge=true" : ""}`);
      setConfirmCut(false);
      setMsg(purge ? "切りました。取り込んだ課題と科目も消しました" : "切りました。取り込んだ課題は残してあります");
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (st === null) return <p className="muted">読み込み中…</p>;
  const c = st.connection;

  return (
    <div className="connect">
      <section className="card">
        <h2>Canvas</h2>
        {c ? (
          <>
            <p>
              <span className={c.status === "error" ? "bad" : "good"}>●</span>{" "}
              {c.status === "error" ? "取り込みに失敗しています" : "つながっています"}
              <span className="muted small"> （URL の末尾 {c.hint}）</span>
            </p>
            <dl className="facts">
              <dt>最後に成功</dt>
              <dd>{ago(c.last_ok_at)}</dd>
              <dt>最後に試した</dt>
              <dd>{ago(c.last_try_at)}</dd>
              {c.last_counts && (
                <>
                  <dt>前回読んだ件数</dt>
                  <dd>{c.last_counts.total}件</dd>
                </>
              )}
            </dl>
            {c.last_error && <p className="error">{c.last_error}</p>}
            <div className="actions">
              <button className="btn" onClick={syncNow} disabled={busy}>
                今すぐ取り込む
              </button>
              {!confirmCut ? (
                <button className="btn danger" onClick={() => setConfirmCut(true)} disabled={busy}>
                  切る
                </button>
              ) : (
                <div className="confirm">
                  <label className="check small">
                    <input type="checkbox" checked={purge} onChange={(e) => setPurge(e.target.checked)} />
                    取り込んだ課題と科目も消す（「出した」の印も消えます）
                  </label>
                  <button className="btn danger" onClick={cut} disabled={busy}>
                    本当に切る
                  </button>
                  <button className="link" onClick={() => setConfirmCut(false)}>
                    やめる
                  </button>
                </div>
              )}
            </div>
            <details className="small">
              <summary>URL を貼り直す</summary>
              <FeedForm url={url} setUrl={setUrl} onSubmit={connect} busy={busy} />
            </details>
          </>
        ) : (
          <>
            <p className="muted">まだつながっていません。</p>
            <Steps />
            <FeedForm url={url} setUrl={setUrl} onSubmit={connect} busy={busy} />
          </>
        )}
        {msg && <p className="note">{msg}</p>}
        {err && <p className="error">{err}</p>}
      </section>

      <section className="card small">
        <h3>FLASH が預かるもの・預からないもの</h3>
        <ul className="plain">
          <li>
            <b>預かる:</b> カレンダーフィードの URL（暗号化して保存）。読めるのは Canvas
            のカレンダーに出る課題と予定だけで、成績・提出物・メッセージは読めません。
          </li>
          <li>
            <b>預からない:</b> 大学のパスワード、Canvas のアクセストークン。
          </li>
          <li>
            「切る」を押すと、預けた URL は FLASH から消えます。
          </li>
          <li>
            FLASH の画面や機能から、ほかの人（管理者も）があなたの課題を見ることはできません。
            ただし課題の中身そのものは暗号化していないので、サーバーを動かしている管理者が
            データベースを直接のぞくことは、技術的にはできます。
          </li>
          <li>
            フィードには「提出したか」が載らないので、出した課題は締切一覧で自分でチェックしてください。
          </li>
        </ul>
      </section>
    </div>
  );
}

function Steps() {
  return (
    <ol className="steps">
      <li>パソコンのブラウザで Canvas を開く</li>
      <li>左のメニューの「カレンダー」を開く</li>
      <li>右側の「カレンダーフィード」を押す</li>
      <li>出てきた URL をコピーして、下に貼る</li>
    </ol>
  );
}

function FeedForm(p: {
  url: string;
  setUrl: (s: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  busy: boolean;
}) {
  return (
    <form className="feed" onSubmit={p.onSubmit}>
      <input
        type="url"
        inputMode="url"
        autoComplete="off"
        placeholder="https://nu.instructure.com/feeds/calendars/user_….ics"
        value={p.url}
        onChange={(e) => p.setUrl(e.target.value)}
        required
      />
      <button className="btn primary" type="submit" disabled={p.busy}>
        {p.busy ? "確かめています…" : "つなぐ"}
      </button>
    </form>
  );
}
