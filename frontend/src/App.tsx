import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, ApiError, type Me } from "./api";
import Connect from "./pages/Connect";
import Courses from "./pages/Courses";
import Home from "./pages/Home";
import Login from "./pages/Login";

// 画面の骨組み。ログインしていなければログイン画面へ、していれば上の帯＋中身＋下のタブ。
export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = 確認中
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/api/me"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setMe(null);
      else throw e;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (me === undefined) return <div className="boot">⚡</div>;

  if (me === null) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLoggedIn={refresh} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  const logout = async () => {
    await api.post("/api/auth/logout");
    setMe(null);
    navigate("/login");
  };

  return (
    <div className="shell">
      <header className="top">
        <span className="brand">
          <span className="bolt">⚡</span>FLASH
        </span>
        <span className="who" title={me.email}>
          {me.name ?? me.email}
          {me.is_admin && <span className="tag">管理者</span>}
        </span>
        <button className="link" onClick={logout}>
          ログアウト
        </button>
      </header>

      <main className="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/courses" element={<Courses />} />
          <Route path="/connect" element={<Connect />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <nav className="tabs">
        <NavLink to="/" end>
          締切
        </NavLink>
        <NavLink to="/courses">科目</NavLink>
        <NavLink to="/connect">つなぐ</NavLink>
      </nav>
    </div>
  );
}
