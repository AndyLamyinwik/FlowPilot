FROM node:24.22.1-alpine AS build

WORKDIR /app/frontend

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
ARG VITE_API_BASE_URL=/api
RUN VITE_API_BASE_URL="$VITE_API_BASE_URL" npm run build

FROM node:24.22.1-alpine AS runtime

ENV NODE_ENV=production \
    FLOWPILOT_FRONTEND_HOST=0.0.0.0 \
    FLOWPILOT_FRONTEND_PORT=5173

WORKDIR /app/frontend
COPY --from=build /app/frontend/dist ./dist
COPY server.mjs ./server.mjs
USER node

EXPOSE 5173

CMD ["node", "server.mjs"]
