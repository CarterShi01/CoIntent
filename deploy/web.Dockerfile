# syntax=docker/dockerfile:1
FROM node:24-alpine AS build
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM alpine:3.22
WORKDIR /dist
COPY --from=build /src/web/dist ./
CMD ["sh", "-c", "rm -rf /out/* /out/.[!.]* /out/..?* 2>/dev/null || true; cp -a /dist/. /out/; echo 'CoIntent web bundle exported'; ls -la /out"]
