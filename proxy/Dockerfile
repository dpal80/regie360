# syntax=docker/dockerfile:1
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

# 3) Phone Island: il widget ufficiale di Nethesis (GPL-3.0), non modificato, a versione fissa e con
#    impronta verificata. Si scarica solo qui, durante la build: in sede non serve internet.
ARG PHONE_ISLAND=https://raw.githubusercontent.com/nethesis/phone-island/v1.0.15/dist-widget
ADD --chmod=644 --checksum=sha256:044db625971f33be5c733576463b93e4b11ee3526224751aaba6006c1a5ad46c \
    ${PHONE_ISLAND}/index.widget.js /usr/share/nginx/html/phone-island/index.widget.js
ADD --chmod=644 --checksum=sha256:c4743af940c47548aa00eddd7418443e52dd3b67c89d7d0952cbdeff8140284a \
    ${PHONE_ISLAND}/index.widget.css /usr/share/nginx/html/phone-island/index.widget.css
# Il foglio di stile chiederebbe due font a siti esterni: si tolgono, il CRM non usa risorse esterne.
RUN sed -i 's/@import "[^"]*";//g' /usr/share/nginx/html/phone-island/index.widget.css \
    && chmod 755 /usr/share/nginx/html/phone-island
