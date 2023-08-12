# Fetch the mc command line client
FROM alpine:3.18.3
RUN apk update && apk add ca-certificates wget && update-ca-certificates
RUN ARCH=$(uname -m | sed s/aarch64/arm64/ | sed s/x86_64/amd64/) && wget -O /tmp/mc "https://dl.minio.io/client/mc/release/linux-${ARCH}/mc"
RUN chmod +x /tmp/mc

# Then build our backup image
FROM mariadb:11.0.2-jammy

# Install the latest ca-certificates package to resolve Lets Encrypt auth issues
RUN apt-get update && apt-get install ca-certificates

COPY --from=0 /tmp/mc /usr/bin/mc

ENV MINIO_SERVER=""
ENV MINIO_BUCKET="backups"
ENV MINIO_ACCESS_KEY=""
ENV MINIO_SECRET_KEY=""
ENV MINIO_API_VERSION="S3v4"

ENV DATE_FORMAT="+%Y-%m-%d"

ADD entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT [ "/app/entrypoint.sh" ]
