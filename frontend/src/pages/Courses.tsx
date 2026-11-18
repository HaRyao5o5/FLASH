import { useCallback, useEffect, useState } from "react";
import { api, type Course } from "../api";

// 科目の一覧。Canvas のコース名から自動で作られる。
// 呼び名と「隠す」は本人が決める値で、取り込み直しても上書きされない。
export default function Courses() {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => setCourses(await api.get<Course[]>("/api/courses")), []);
  useEffect(() => {
    load();
  }, [load]);

  const patch = async (id: string, body: Partial<Pick<Course, "hidden" | "display_name">>) => {
    setErr("");
    try {
      await api.patch(`/api/courses/${id}`, body);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  if (courses === null) return <p className="muted">読み込み中…</p>;
  if (courses.length === 0)
    return <div className="card empty">まだ科目がありません。Canvas をつなぐと、課題のある科目から自動で並びます。</div>;

  return (
    <div className="courses">
      <p className="muted small">
        Canvas のコース名から作っています。曜日・時限はコース名に入っているものを読んでいます。
        呼び名を変えたり、関係ない科目を隠したりできます。
      </p>
      {err && <p className="error">{err}</p>}
      {courses.map((c) => (
        <div key={c.id} className={`row course-row${c.hidden ? " hidden" : ""}`}>
          <div className="slotbox">{c.slot ?? "—"}</div>
          <div className="body">
            {editing === c.id ? (
              <form
                className="inline"
                onSubmit={(e) => {
                  e.preventDefault();
                  patch(c.id, { display_name: draft });
                  setEditing(null);
                }}
              >
                <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={c.name} autoFocus />
                <button className="btn small" type="submit">
                  保存
                </button>
                <button className="link" type="button" onClick={() => setEditing(null)}>
                  やめる
                </button>
              </form>
            ) : (
              <div className="title">
                {c.display_name ?? c.name}
                <button
                  className="link small"
                  onClick={() => {
                    setEditing(c.id);
                    setDraft(c.display_name ?? "");
                  }}
                >
                  呼び名
                </button>
              </div>
            )}
            <div className="meta">
              {[c.teacher, c.term && `${c.term}期`, `課題・予定 ${c.item_count}件`].filter(Boolean).join(" ・ ")}
              {c.display_name && <span className="muted"> （元の名前: {c.name}）</span>}
            </div>
          </div>
          <button className="btn small" onClick={() => patch(c.id, { hidden: !c.hidden })}>
            {c.hidden ? "表示する" : "隠す"}
          </button>
        </div>
      ))}
    </div>
  );
}
