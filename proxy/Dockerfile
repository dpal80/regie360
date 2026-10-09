# 1) build del frontend React
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) Nginx: HTTPS, file statici del frontend e inoltro /api al backend
FROM nginx:1.27-alpine
RUN apk add --no-cache openssl
COPY proxy/nginx.conf /etc/nginx/conf.d/default.conf
COPY proxy/certificato.sh /docker-entrypoint.d/05-certificato.sh
RUN chmod +x /docker-entrypoint.d/05-certificato.sh
COPY --from=frontend /src/dist /usr/share/nginx/html
