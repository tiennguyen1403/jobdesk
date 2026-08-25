import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        host: true,
        port: 5173,
        // usePolling giúp HMR hoạt động ổn định khi chạy trong Docker trên Windows
        watch: { usePolling: true },
    },
});
