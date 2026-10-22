# AAGAM on a server or another machine. Her laptop doesn't need Docker (see README, "Install").
#
#   docker build -t aagam .
#   docker run -d --name aagam -p 127.0.0.1:8765:8765 -v aagam-data:/data aagam
#
# Linux has no Windows OCR: scanned pages aren't read (text PDFs and Office files are).
# MCA form filling needs her desktop browser, so it isn't available here either.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md /build/
COPY src /build/src
RUN pip install /build \
    && rm -rf /build \
    && useradd --create-home --uid 1000 aagam \
    && mkdir /data \
    && chown aagam:aagam /data

# Listen on every interface inside the container; publish the port on the host's
# 127.0.0.1 only. AAGAM answers only requests addressed to 127.0.0.1 or localhost.
ENV AAGAM_HOME=/data \
    AAGAM_BIND=0.0.0.0 \
    AAGAM_PORT=8765
VOLUME ["/data"]
EXPOSE 8765
USER aagam
WORKDIR /home/aagam

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('AAGAM_PORT', '8765'), timeout=3)"

CMD ["aagam", "serve"]
