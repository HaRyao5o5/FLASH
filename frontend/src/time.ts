// 日時の見せ方。表示は全部日本時間で決め打ち（日本の大学向けなので）。

const TZ = "Asia/Tokyo";


/** 日本時間での「その日」を YYYY-MM-DD で */
export function jstDay(d: Date): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: TZ }).format(d);
}

function dayDiff(a: Date, b: Date): number {
  const da = Date.parse(jstDay(a) + "T00:00:00Z");
  const db = Date.parse(jstDay(b) + "T00:00:00Z");
  return Math.round((da - db) / 86400000);
}

function hm(d: Date): string {
  return new Intl.DateTimeFormat("ja-JP", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d);
}

function md(d: Date): string {
  const p = new Intl.DateTimeFormat("ja-JP", { timeZone: TZ, month: "numeric", day: "numeric", weekday: "short" })
    .formatToParts(d);
  const get = (t: string) => p.find((x) => x.type === t)?.value ?? "";
  return `${get("month")}/${get("day")}(${get("weekday")})`;
}

/** 締切の見出し: 「今日 23:59」「明日」「11/27(金) 23:59」 */
export function dueLabel(iso: string | null, allDay: boolean, now = new Date()): string {
  if (!iso) return "日付なし";
  const d = new Date(iso);
  const diff = dayDiff(d, now);
  const day = diff === 0 ? "今日" : diff === 1 ? "明日" : diff === -1 ? "昨日" : md(d);
  return allDay ? day : `${day} ${hm(d)}`;
}

/** 残り時間: 「あと3時間」「あと2日」「2日過ぎ」 */
export function remaining(iso: string | null, now = new Date()): string {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - now.getTime();
  const abs = Math.abs(ms);
  const h = Math.floor(abs / 3600000);
  const text = h < 1 ? `${Math.max(1, Math.floor(abs / 60000))}分` : h < 48 ? `${h}時間` : `${Math.floor(h / 24)}日`;
  return ms >= 0 ? `あと${text}` : `${text}過ぎ`;
}

/** 「さっき」「5分前」「3時間前」「11/18 14:02」 */
export function ago(iso: string | null, now = new Date()): string {
  if (!iso) return "まだ";
  const d = new Date(iso);
  const s = (now.getTime() - d.getTime()) / 1000;
  if (s < 60) return "さっき";
  if (s < 3600) return `${Math.floor(s / 60)}分前`;
  if (s < 86400) return `${Math.floor(s / 3600)}時間前`;
  return `${md(d)} ${hm(d)}`;
}

export type Bucket = "overdue" | "today" | "tomorrow" | "week" | "later" | "none";

export const BUCKET_LABEL: Record<Bucket, string> = {
  overdue: "過ぎている",
  today: "今日",
  tomorrow: "明日",
  week: "今週中（7日以内）",
  later: "その先",
  none: "日付なし",
};

export function bucketOf(iso: string | null, now = new Date()): Bucket {
  if (!iso) return "none";
  const d = new Date(iso);
  if (d.getTime() < now.getTime()) return "overdue";
  const diff = dayDiff(d, now);
  if (diff <= 0) return "today";
  if (diff === 1) return "tomorrow";
  if (diff <= 7) return "week";
  return "later";
}

export const weekday = (i: number | null) => (i == null ? "" : "月火水木金土日"[i] ?? "");

