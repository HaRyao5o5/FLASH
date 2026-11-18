import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type CanvasStatus, type Item } from "../api";
import { ago, BUCKET_LABEL, bucketOf, dueLabel, remaining, type Bucket } from "../time";

const ORDER: Bucket[] = ["overdue", "today", "tomorrow", "week", "later", "none"];

// 締切の一覧。FLASH の顔。
//
// フィードには「提出したか」が載らないので、「出した」は本人が押す。
// 押したものは下の「終わったもの」にまとまり、いつでも戻せる。
export default function Home() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [status, setStatus] = useState<CanvasStatus | null>(null);
  const [showDone, setShowDone] = useState(false);
  const [showEvents, setShowEvents] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const [it, st] = await Promise.all([api.get<Item[]>("/api/items"), api.get<CanvasStatus>("/api/canvas")]);
    setItems(it);
    setStatus(st);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (it: Item) => {
    const done = !it.done_at;
    // 押した瞬間に見た目を変える（待たせない）。失敗したら戻す
    setItems((xs) => xs?.map((x) => (x.id === it.id ? { ...x, done_at: done ? new Date().toISOString() : null } : x)) ?? xs);
    try {
      await api.patch(`/api/items/${it.id}`, { done });
    } catch (e) {
      setItems((xs) => xs?.map((x) => (x.id === it.id ? it : x)) ?? xs);
      setMsg((e as Error).message);
    }
  };

  const syncNow = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.post<CanvasStatus>("/api/canvas/sync");
      const c = r.counts;
      setMsg(c ? summary(c.new, c.due_changed, c.gone) : "取り込みました");
      await load();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const groups = useMemo(() => {
    const now = new Date();
    const open: Record<Bucket, Item[]> = { overdue: [], today: [], tomorrow: [], week: [], later: [], none: [] };
    const done: Item[] = [];
    for (const it of items ?? []) {
      if (!showEvents && it.kind === "event") continue;
      if (it.done_at) done.push(it);
      else if (it.gone_at) continue; // 消えたもので未完了のものは下の「消えたもの」へ
      else open[bucketOf(it.due_at, now)].push(it);
    }
    const gone = (items ?? []).filter((it) => it.gone_at && !it.done_at);
    return { open, done, gone };
  }, [items, showEvents]);

  if (items === null || status === null) return <p className="muted">読み込み中…</p>;

  if (!status.connected && items.length === 0) {
    return (
      <div className="card hero">
        <h2>まず Canvas をつなぎましょう</h2>
        <p>Canvas の「カレンダーフィード」の URL を貼るだけで、課題の締切がここに並びます。</p>
        <Link className="btn primary" to="/connect">
          つなぐ
        </Link>
      </div>
    );
  }

  const openCount = ORDER.reduce((n, b) => n + groups.open[b].length, 0);
  const conn = status.connection;

  return (
    <div className="home">
      <div className="bar">
        <div className="muted small">
          {conn ? (
            <>
              {conn.status === "error" ? <span className="bad">取り込みに失敗中</span> : "最終取り込み"}{" "}
              {ago(conn.last_ok_at)}
            </>
          ) : (
            <span className="bad">Canvas は切ってあります</span>
          )}
        </div>
        {conn && (
          <button className="btn small" onClick={syncNow} disabled={busy}>
            {busy ? "取り込み中…" : "今すぐ取り込む"}
          </button>
        )}
      </div>
      {conn?.status === "error" && conn.last_error && (
        <p className="error">
          {conn.last_error} <Link to="/connect">つなぎ直す</Link>
        </p>
      )}
      {msg && <p className="note">{msg}</p>}

      <label className="check small">
        <input type="checkbox" checked={showEvents} onChange={(e) => setShowEvents(e.target.checked)} />
        課題以外の予定も出す
      </label>

      {openCount === 0 && <div className="card empty">残っている締切はありません 🎉</div>}

      {ORDER.map((b) =>
        groups.open[b].length ? (
          <section key={b} className={`group g-${b}`}>
            <h3>
              {BUCKET_LABEL[b]} <span className="count">{groups.open[b].length}</span>
            </h3>
            {groups.open[b].map((it) => (
              <Row key={it.id} it={it} onToggle={toggle} />
            ))}
          </section>
        ) : null,
      )}

      {groups.gone.length > 0 && (
        <section className="group g-gone">
          <h3>
            Canvas から消えたもの <span className="count">{groups.gone.length}</span>
          </h3>
          <p className="muted small">先生が削除・非公開にした可能性があります。念のため Canvas で確かめてください。</p>
          {groups.gone.map((it) => (
            <Row key={it.id} it={it} onToggle={toggle} />
          ))}
        </section>
      )}

      {groups.done.length > 0 && (
        <section className="group g-done">
          <button className="link" onClick={() => setShowDone((v) => !v)}>
            {showDone ? "▾" : "▸"} 終わったもの（{groups.done.length}）
          </button>
          {showDone && groups.done.map((it) => <Row key={it.id} it={it} onToggle={toggle} />)}
        </section>
      )}
    </div>
  );
}

function Row({ it, onToggle }: { it: Item; onToggle: (it: Item) => void }) {
  const isEvent = it.kind === "event";
  return (
    <div className={`row${it.done_at ? " done" : ""}${it.gone_at ? " gone" : ""}`}>
      {isEvent ? (
        <span className="dot" title="予定" />
      ) : (
        <input
          type="checkbox"
          className="tick"
          checked={!!it.done_at}
          onChange={() => onToggle(it)}
          aria-label="出した"
          title="出した"
        />
      )}
      <div className="body">
        <div className="title">
          {it.url ? (
            <a href={it.url} target="_blank" rel="noreferrer">
              {it.title}
            </a>
          ) : (
            it.title
          )}
          {isEvent && <span className="tag">予定</span>}
          {it.prev_due_at && (
            <span className="tag warn" title={`前の締切: ${dueLabel(it.prev_due_at, it.all_day)}`}>
              締切変更
            </span>
          )}
        </div>
        <div className="meta">
          {it.course_name && (
            <span className="course">
              {it.course_name}
              {it.course_slot && <span className="slot">{it.course_slot}</span>}
            </span>
          )}
        </div>
      </div>
      <div className="due">
        <div>{dueLabel(it.due_at, it.all_day)}</div>
        {!it.done_at && !isEvent && <div className="muted small">{remaining(it.due_at)}</div>}
      </div>
    </div>
  );
}

export function summary(n: number, changed: number, gone: number): string {
  const parts = [];
  if (n) parts.push(`新しく${n}件`);
  if (changed) parts.push(`締切変更${changed}件`);
  if (gone) parts.push(`消えた${gone}件`);
  return parts.length ? `取り込みました（${parts.join("・")}）` : "取り込みました（変化なし）";
}
