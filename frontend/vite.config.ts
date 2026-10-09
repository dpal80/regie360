import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In sviluppo le chiamate /api vanno al backend locale.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": process.env.VITE_BACKEND ?? "http://localhost:8000" },
  },
});
