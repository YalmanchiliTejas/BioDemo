import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({ plugins: [react()], server: { port: 5180, host: "127.0.0.1", proxy: { '/v1': 'http://127.0.0.1:8100', '/api/pharma': 'http://127.0.0.1:8000', '/api/cmo-ingestion': 'http://127.0.0.1:8000' } } });
