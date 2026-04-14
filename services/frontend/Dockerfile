# Multi-stage build: Node build + nginx serve
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps first for better layer caching
COPY services/frontend/package.json services/frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps

# Copy source and build
COPY services/frontend/ .
ARG VITE_API_URL
ARG VITE_API_KEY
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_KEY=$VITE_API_KEY
RUN npm run build

# --- Runtime ---
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# SPA fallback + gzip + long-cache assets
RUN cat > /etc/nginx/conf.d/default.conf <<'EOF'
server {
    listen 80;
    server_name _;

    gzip on;
    gzip_types text/plain application/javascript text/css application/json image/svg+xml;
    gzip_min_length 1024;

    root /usr/share/nginx/html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
