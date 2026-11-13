ARG DOCKER_REGISTRY=docker.io
FROM ${DOCKER_REGISTRY}/library/node:22-alpine AS build
WORKDIR /app/frontend-admin
COPY frontend-admin/package*.json ./
RUN npm ci && ln -s /app/frontend-admin/node_modules /app/node_modules
COPY frontend-admin/ ./
COPY frontend/src/ /app/frontend/src/

# Vite 会在构建阶段把公开 API 地址写入浏览器产物。修改地址后必须重建镜像。
ARG VITE_API_URL=http://localhost:8001
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM ${DOCKER_REGISTRY}/library/nginx:1.27-alpine
COPY frontend-admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend-admin/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
