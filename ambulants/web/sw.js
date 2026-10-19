// Le service worker : garder les tuiles IGN, et la page quand le réseau
// manque.
//
// **Les tuiles d'abord.** Une commune rurale a souvent un réseau faible ;
// les tuiles déjà vues (plan et satellite IGN, Licence Ouverte Etalab 2.0)
// sont servies depuis l'appareil, sans attendre le réseau. Leur nombre est
// plafonné pour ne pas remplir le téléphone.
//
// **Le reste, réseau d'abord.** La page, ses fichiers et la carte des
// annonces passent par le réseau quand il répond ; la copie gardée ne sert
// que quand il ne répond pas. Rien n'est donc servi périmé à qui a du
// réseau.
//
// **Jamais gardé** : ce qui regarde un compte (session, mon compte,
// modération, administration) et toute écriture.
'use strict';

const CACHE_TUILES = 'tuiles-ign-v1';
const CACHE_PAGES = 'pages-v1';
const TUILES_MAX = 3000;

function estUneTuileIgn(url) {
  return /^https:\/\/data\.geopf\.fr\/wmts\?/.test(url) && /REQUEST=GetTile/i.test(url)
    && /LAYER=(GEOGRAPHICALGRIDSYSTEMS\.PLANIGNV2|ORTHOIMAGERY\.ORTHOPHOTOS)&/.test(url);
}

function aGarder(url, methode) {
  if (methode !== 'GET') return false;
  let u;
  try { u = new URL(url); } catch (_) { return false; }
  if (typeof self !== 'undefined' && self.location && u.origin !== self.location.origin) return false;
  if (/^\/api\/(session|moi|moderation|admin|annonces)/.test(u.pathname)) return false;
  return u.pathname === '/' || u.pathname.startsWith('/static/') || u.pathname === '/api/carte'
    || u.pathname === '/api/categories';
}

let aRanger = 0;
async function elaguer(cache) {
  const cles = await cache.keys();
  // Les plus anciennes d'abord : l'ordre des clés est celui de l'ajout.
  for (let i = 0; i < cles.length - TUILES_MAX; i += 1) await cache.delete(cles[i]);
}

async function tuile(requete) {
  const url = requete.url;
  const cache = await caches.open(CACHE_TUILES);
  const gardee = await cache.match(url);
  if (gardee) return gardee;
  // Demandée en CORS (la Géoplateforme le permet) : une réponse opaque
  // pèserait plusieurs mégaoctets dans le quota du navigateur, quelle que
  // soit sa taille réelle (leçon de WAY2NAV).
  const r = await fetch(url, { mode: 'cors', credentials: 'omit' });
  if (r.ok && /^image\//.test(r.headers.get('content-type') || '')) {
    cache.put(url, r.clone()).then(() => {
      aRanger += 1;
      if (aRanger >= 50) { aRanger = 0; return elaguer(cache); }
      return null;
    }).catch(() => { /* quota plein : on sert sans garder */ });
  }
  return r;
}

async function reseauDAbord(requete) {
  const cache = await caches.open(CACHE_PAGES);
  try {
    const r = await fetch(requete);
    if (r.ok) cache.put(requete, r.clone());
    return r;
  } catch (err) {
    const gardee = await cache.match(requete);
    if (gardee) return gardee;
    throw err;
  }
}

if (typeof self !== 'undefined' && typeof self.addEventListener === 'function' && typeof module === 'undefined') {
  self.addEventListener('install', () => self.skipWaiting());
  self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
  self.addEventListener('fetch', (e) => {
    const { url, method } = e.request;
    if (method === 'GET' && estUneTuileIgn(url)) e.respondWith(tuile(e.request));
    else if (aGarder(url, method)) e.respondWith(reseauDAbord(e.request));
  });
}

// Pour les essais sous Node seulement.
if (typeof module !== 'undefined') module.exports = { estUneTuileIgn, aGarder };
