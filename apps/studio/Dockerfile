# Build the SPA, then serve it from nginx with the API reverse-proxied.
FROM node:22-alpine AS build
WORKDIR /app

COPY apps/studio/package.json apps/studio/package-lock.json* ./
RUN npm install

COPY apps/studio/ ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY apps/studio/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
