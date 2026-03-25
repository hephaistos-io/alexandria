import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    host: true,
    proxy: {
      "/api": "http://monitoring-api:8000",
      "/ws": {
        target: "http://monitoring-api:8000",
        ws: true,
      },
    },
  },
});
