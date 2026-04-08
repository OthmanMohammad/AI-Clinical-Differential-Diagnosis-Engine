FROM node:20-alpine AS builder

WORKDIR /app

COPY services/frontend/package.json services/frontend/package-lock.json* ./
RUN npm ci

COPY services/frontend/ .
RUN npm run build

# --- Serve static files ---
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# SPA fallback
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
