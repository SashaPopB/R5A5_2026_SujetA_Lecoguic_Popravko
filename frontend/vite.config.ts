import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En développement, Vite relaie /api vers Flask : le front et l'API sont
// vus sur la même origine, ce qui permet des cookies SameSite=Strict sans
// configuration CORS (le flux temps réel /api/evenements passe aussi).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:5000", changeOrigin: true },
    },
  },
});
