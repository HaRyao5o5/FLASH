// サーバーとのやりとりは全部ここを通す。
//
// 書き換え系（POST/PUT/PATCH/DELETE）には必ず X-FLASH: 1 を付ける。
// サーバー側はこれが無い書き換えを断る（別のサイトから勝手に操作させない仕掛け。backend/app/main.py）。

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "X-FLASH": "1" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!res.ok) {
    let msg = `うまくいきませんでした（${res.status}）`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* 本文が JSON でない */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T>(p: string, b: unknown) => request<T>("PUT", p, b),
  patch: <T>(p: string, b: unknown) => request<T>("PATCH", p, b),
  del: <T>(p: string) => request<T>("DELETE", p),
};

// ---- 型（サーバーの返す形） ----

export type Me = { id: string; email: string; name: string | null; is_admin: boolean };

export type Counts = {
  total: number;
  new: number;
  due_changed: number;
  gone: number;
  back: number;
  courses_new: number;
  skipped_gone_check: boolean;
};

export type Connection = {
  hint: string | null;
  status: "new" | "ok" | "error";
  last_try_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  last_counts: Counts | null;
  created_at: string;
};

export type CanvasStatus = { connected: boolean; connection: Connection | null; counts?: Counts };

export type Item = {
  id: string;
  kind: "assignment" | "event";
  title: string;
  due_at: string | null;
  all_day: boolean;
  url: string | null;
  description: string | null;
  prev_due_at: string | null;
  due_changed_at: string | null;
  first_seen_at: string;
  gone_at: string | null;
  done_at: string | null;
  course_id: string | null;
  course_name: string | null;
  course_slot: string | null;
};

export type Course = {
  id: string;
  ext_key: string;
  name: string;
  display_name: string | null;
  teacher: string | null;
  term: string | null;
  day_of_week: number | null;
  period: number | null;
  slot: string | null;
  hidden: boolean;
  item_count: number;
};
