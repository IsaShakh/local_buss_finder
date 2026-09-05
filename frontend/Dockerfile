# syntax=docker/dockerfile:1.7
FROM node:24-bookworm-slim AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM dependencies AS development
COPY frontend/ ./
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM dependencies AS build
ARG VITE_SENTRY_DSN=""
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine AS production
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
