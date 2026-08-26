FROM debian:bookworm-slim AS build
ARG ODIN_COMMIT=38fcd537dd6c7dec7ef596e861551f1b278f2f98
ARG DDS_UPSTREAM_COMMIT=7219c956f4ed9a9f8d1585e9a1a2c57465745ac5
ARG DDS_A_SHA256=e5c7bcdcf96d3ed24b14b2840303a0d0936b05419de463809f68982c565c7f4c
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone https://github.com/enerqi/odin-dds.git odin-dds && git -C odin-dds checkout "$ODIN_COMMIT" && grep -q "$DDS_UPSTREAM_COMMIT" odin-dds/external/dds/VENDORED.md && make -C odin-dds/src && test "$(sha256sum odin-dds/lib/dds.a | awk '{print $1}')" = "$DDS_A_SHA256"
COPY r86/r86_dds_daemon.cpp /src/r86_dds_daemon.cpp
RUN g++ -std=c++17 -O3 -I odin-dds/external/dds/include /src/r86_dds_daemon.cpp odin-dds/lib/dds.a -pthread -o /src/r86_dds_daemon

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 libstdc++6 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/r86_dds_daemon /app/r86_dds_daemon
COPY r86/r86_dds_server.py /app/r86_dds_server.py
ENV PORT=8080 HOST=0.0.0.0 DDS_RUNNER=/app/r86_dds_daemon DDS_THREADS=2 DDS_BATCH_SIZE=24 DDS_MAX_ITEMS=40 DDS_REQUEST_TIMEOUT_SEC=20
EXPOSE 8080
CMD ["python3","/app/r86_dds_server.py"]
