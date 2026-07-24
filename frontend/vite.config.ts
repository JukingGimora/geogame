import { defineConfig } from "vite";
import uni from "@dcloudio/vite-plugin-uni";

// https://vitejs.dev/config/
export default defineConfig({
  base: "./",
  plugins: [uni()],
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
});
