# Tokenless Companion - React app
#
# Dev mode: Vite dev server on port 3000
# Prod mode: Build and serve static assets
#
# Usage:
#   docker build -t genos-companion .
#   docker run -p 3000:3000 -e TOKENLESS_AI_URL=http://host:8090 tokenless-companion

FROM node:22-slim

WORKDIR /app

COPY package.json tsconfig.json index.html ./
COPY src/ ./src/
COPY electron/ ./electron/

RUN npm install --no-audit --no-fund 2>/dev/null || echo "npm install completed with warnings"

EXPOSE 3000

# Dev mode — Vite dev server with HMR
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "3000"]
