FROM node:22-alpine

WORKDIR /app

# Install dependencies first (cached layer)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Source files are bind-mounted at runtime for hot reload,
# but we copy them here too so the image works standalone.
COPY frontend/ .

EXPOSE 5173

CMD ["npx", "vite", "--host"]
