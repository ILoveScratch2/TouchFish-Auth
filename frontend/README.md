# TouchFish Auth (FRONTEND)

React 单页应用实现的 TouchFish Auth 前端界面

项目请参考主 [README](../README.md)。


基于 
- Vite
- React 19
- TypeScript
- React Router
- Tailwind CSS
- framer-motion
- lucide-react


## 本地开发

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

dev server 的 `/api` 与 `/.well-known` 代理到 `http://127.0.0.1:8000`（见 `vite.config.ts`）。

## 构建与部署

```bash
npm run build        # tsc -b && vite build → dist/
```

产物 `dist/` 会被后端直接托管。


```bash
npx tsc -b
npm run format:check
npm run build
```

