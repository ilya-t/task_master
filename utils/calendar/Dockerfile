FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client docker-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY setup.sh .
COPY src ./src
COPY utils/calendar/src ./utils/calendar/src

RUN mkdir -p utils/calendar/repo_storage \
    && bash ./setup.sh \
    && chmod +x utils/calendar/src/docker-entrypoint.sh

WORKDIR /app/utils/calendar/src
EXPOSE 37200
ENTRYPOINT ["./docker-entrypoint.sh"]
