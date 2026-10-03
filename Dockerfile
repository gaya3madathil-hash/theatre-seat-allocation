FROM gcc:13 AS build
WORKDIR /src
COPY server.c .
RUN gcc -O2 -Wall -o server server.c

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /src/server .
COPY public ./public
ENV PORT=8080
EXPOSE 8080
CMD ["./server"]
