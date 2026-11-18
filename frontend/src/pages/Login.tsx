import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";

type Options = { google: boolean; dev: boolean };

const ERRORS: Record<string, string> = {
  google: "Google でのログインがうまくいきませんでした。もう一度どうぞ",
  unverified: "メールアドレスが確認済みの Google アカウントでログインしてください",
};

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [opt, setOpt] = useState<Options | null>(null);
  const [email, setEmail] = useState("");
  const [err, setErr] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    api.get<Options>("/api/auth/options").then(setOpt);
    const e = params.get("error");
    if (e) setErr(params.get("why") || ERRORS[e] || "ログインできませんでした");
  }, [params]);

  const devLogin = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setErr("");
    try {
      await api.post("/api/auth/dev-login", { email });
      onLoggedIn();
      navigate("/");
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="login">
      <div className="login-card">
        <div className="login-mark">⚡</div>
        <h1>FLASH</h1>
        <p className="muted">大学の課題と予定を、ひとつの場所に。</p>

        {err && <p className="error">{err}</p>}

        {opt?.google && (
          <a className="btn primary wide" href="/auth/google">
            大学の Google アカウントでログイン
          </a>
        )}

        {opt?.dev && (
          <form className="dev" onSubmit={devLogin}>
            <p className="muted small">開発用ログイン（手元で動かしているときだけ出ます）</p>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <button className="btn wide" type="submit">
              このメールで入る
            </button>
          </form>
        )}

        {opt && !opt.google && !opt.dev && <p className="error">ログインの方法が設定されていません</p>}

        <p className="muted small fine">
          FLASH は大学のパスワードを預かりません。ログインは Google に確かめてもらい、
          受け取るのは名前とメールアドレスだけです。
        </p>
      </div>
    </div>
  );
}
