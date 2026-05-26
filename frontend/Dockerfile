# syntax=docker/dockerfile:1

# Stage 1: build
FROM node:22-alpine AS builder
WORKDIR /app

# Layer: deps (cached until package.json / package-lock.json changes)
COPY package.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install

# Layer: source
COPY . .
RUN npm run build

# Stage 2: serve static files with nginx
FROM nginx:alpine AS runner
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
