# Copies locales des bibliothèques de carte

```
leaflet.js    dist/leaflet.js de leaflet@1.9.4
leaflet.css   dist/leaflet.css de la même version
```

Copiées telles quelles depuis WAY2NAV (jsd2/paddle, `paddle_france/web/vendor/`),
qui les a prises du registre npm, empreinte vérifiée :
`leaflet@1.9.4  sha1 23fae724e282fa25745aff82ca4d394748db7d8d`.

Servies par le site lui-même : pas de dépendance à un CDN, et la politique de
sécurité du contenu peut se limiter à `script-src 'self'`.
