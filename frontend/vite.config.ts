import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 開発中（npm run dev）は 5173 番で画面を出し、/api と /auth は FastAPI（8000番）へ回す。
// 本番は FastAPI が組み立て済みの dist/ を直接配るので、この転送は使わない。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
    },
  },
});
