# Image de l'application : la bibliothèque standard de Python, rien d'autre.
FROM python:3.12-slim

# Sorties non tamponnées : les journaux de l'hébergeur restent lisibles en direct.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AMBULANTS_DB=/data/ambulants.sqlite3

WORKDIR /app
COPY pyproject.toml README.md ./
COPY ambulants ./ambulants
RUN pip install --no-cache-dir .

# La base vit sur un volume : sans lui, comptes et annonces disparaissent au
# premier redémarrage du conteneur.
RUN mkdir -p /data && useradd --create-home --uid 10001 ambulants \
    && chown -R ambulants:ambulants /data /app
VOLUME ["/data"]
USER ambulants

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8000') + '/api/sante', timeout=4)"

# --hote 0.0.0.0 est indispensable en conteneur. AMBULANTS_ENV se pose dans
# l'hébergeur : « production » sur le site public, « test » sur le site de
# test. Sans valeur, le site se croit local : bandeau et noindex.
CMD ["sh", "-c", "ambulants app --hote 0.0.0.0 --port ${PORT:-8000}"]
