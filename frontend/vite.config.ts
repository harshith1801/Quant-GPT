import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],build:{rollupOptions:{output:{manualChunks:{charts:['lightweight-charts'],motion:['motion/react']}}}},server:{proxy:{'/api':'http://127.0.0.1:8000'}}});
