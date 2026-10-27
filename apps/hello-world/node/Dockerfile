FROM node:24-alpine
ENV NODE_ENV=production PORT=8080
WORKDIR /app
COPY src/package.json src/server.js ./
USER 10001:10001
EXPOSE 8080
CMD ["node", "server.js"]
