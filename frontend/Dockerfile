# Frontend Dockerfile

# Stage 1: Build frontend
FROM node:22-slim AS builder
WORKDIR /app

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy backend data (needed for frontend symlink)
COPY backend/src/data ./backend-data/

# Copy frontend source
COPY frontend/ ./

# Fix symlink to use local copy
RUN rm -f src/data/geonames && \
    ln -s ../../backend-data/geonames src/data/geonames

# Build frontend
RUN npm run build

# Stage 2: Production server
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

