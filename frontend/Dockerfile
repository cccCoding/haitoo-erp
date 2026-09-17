FROM node:22-alpine
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
# docker-compose 为开发体验挂载 /app/node_modules；该卷会在依赖清单更新后
# 比镜像中的 node_modules 更旧。启动前同步依赖，避免 Vite 解析到缺失包。
CMD ["sh", "-c", "npm install && npm run dev -- --host 0.0.0.0"]
