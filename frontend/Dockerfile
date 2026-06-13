# Stage 1: Build WASM engine
FROM rust:slim AS wasm-builder
# Prebuilt wasm-pack via cargo-binstall instead of `cargo install` (which compiles
# it from source, ~minutes). wasm-pack ships musl binaries for x86_64 AND aarch64
# linux, so this is fast on CI (x86_64) and local arm64 builds alike; binstall
# falls back to a source build only if a prebuilt is ever missing.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    rustup target add wasm32-unknown-unknown && \
    curl -L --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/cargo-bins/cargo-binstall/main/install-from-binstall-release.sh | bash && \
    cargo binstall -y wasm-pack
WORKDIR /engine
COPY engine/ .
RUN wasm-pack build --no-opt --target web --release --features wasm

# Stage 2: Build frontend
FROM node:24-slim AS builder
WORKDIR /app

# Build arg: empty string for Docker (nginx proxy), undefined for local dev
ARG VITE_API_URL=""

# Copy WASM engine output
COPY --from=wasm-builder /engine/pkg /engine/pkg

# Install dependencies
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Fix geonames: copy actual files instead of broken symlink
RUN rm -rf src/lib/data/geonames
COPY backend/src/data/geonames/ src/lib/data/geonames/

# Build frontend (adapter-static outputs to build/)
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# Stage 3: Production server
FROM nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
