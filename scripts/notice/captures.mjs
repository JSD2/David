// Les captures d'écran de la notice (docs/notice/), prises sur le site
// réel, avec des données d'exemple. Puis le PDF, imprimé par Chromium.
//
//     python3 -m ambulants --base /tmp/notice.sqlite3 app --port 8771 &
//     PLAYWRIGHT_DIR=/chemin/vers/node_modules/ node scripts/notice/captures.mjs
//
// La base doit être neuve : le script crée les comptes et les annonces.
// Les données sont fictives, les lieux réels (Creuse, Haute-Vienne).

import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const DEPOT = path.resolve(ICI, '..', '..');
const SORTIE = path.join(DEPOT, 'docs', 'notice');
const IMAGES = path.join(SORTIE, 'images');
const URL = process.env.NOTICE_URL || 'http://127.0.0.1:8771/';
const BASE = process.env.NOTICE_BASE || '/tmp/notice.sqlite3';
const require = createRequire(process.env.PLAYWRIGHT_DIR || import.meta.url);
const { chromium } = require('playwright');
const MDP = 'un-mot-de-passe-assez-long';

// --lang : sans lui, les champs d'heure s'affichent « 11:00 AM ».
const nav = await chromium.launch({ args: ['--lang=fr-FR'], env: { ...process.env, LANG: 'fr_FR.UTF-8' } });
const erreurs = [];
const pause = (ms) => new Promise(r => setTimeout(r, ms));

async function page(largeur = 1280, hauteur = 860, mobile = false) {
  const ctx = await nav.newContext({ viewport: { width: largeur, height: hauteur }, isMobile: mobile,
    hasTouch: mobile, deviceScaleFactor: mobile ? 2 : 1, locale: 'fr-FR' });
  const p = await ctx.newPage();
  p.on('pageerror', e => erreurs.push(String(e)));
  await p.goto(URL);
  await p.waitForTimeout(600);
  return p;
}
const post = (p, url, corps) => p.evaluate(async ([u, c]) => {
  const r = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(c) });
  return [r.status, await r.json()];
}, [url, corps]);
async function connecter(p, email) {
  await post(p, '/api/session', { email, mot_de_passe: MDP });
  await p.reload(); await p.waitForTimeout(900);
}
/** Attend que les tuiles IGN visibles soient chargées (10 s au plus). */
async function attendreTuiles(p) {
  for (let i = 0; i < 40; i++) {
    const restantes = await p.evaluate(() => [...document.querySelectorAll('.leaflet-tile')]
      .filter(t => !t.classList.contains('leaflet-tile-loaded')).length);
    if (!restantes) return;
    await p.waitForTimeout(250);
  }
}
async function capture(p, nom, options = {}) {
  await p.waitForTimeout(options.attente || 1200);
  await attendreTuiles(p);
  await p.waitForTimeout(300);
  await p.screenshot({ path: path.join(IMAGES, `${nom}.jpg`), type: 'jpeg', quality: 78, ...options.ecran });
  console.log('capture', nom);
}
/** Cadre la carte sur la Creuse et la Haute-Vienne : à l'échelle de la
 *  France, les repères se chevauchent. */
async function cadrer(p, dezoom = 3) {
  await p.fill('#recherche-texte', 'Guéret');
  await p.press('#recherche-texte', 'Enter');
  await p.waitForTimeout(1500);
  await p.locator('#recherche-resultats button').first().click();
  for (let i = 0; i < dezoom; i++) { await p.click('.leaflet-control-zoom-out'); await p.waitForTimeout(350); }
  await p.fill('#recherche-texte', '');
}
/** Ouvre la fiche d'une annonce par son titre (les repères proches se
 *  recouvrent : on clique l'élément lui-même). */
async function ouvrirRepere(p, titre) {
  await p.locator(`.leaflet-marker-icon[title="${titre}"]`).evaluate(e => e.click());
  await p.waitForTimeout(900);
}
const cli = (args) => execSync(`python3 -m ambulants --base ${BASE} ${args}`, { cwd: DEPOT });

// ------------------------------------------------------------------
// Les données d'exemple
// ------------------------------------------------------------------
const prep = await page();
async function compte(corps) {
  await post(prep, '/api/session/fin', {});
  const [statut] = await post(prep, '/api/comptes', { mot_de_passe: MDP, conditions_acceptees: true, ...corps });
  if (statut !== 201) throw new Error(`inscription ${corps.pseudo} : ${statut}`);
}
const recherche = (o) => post(prep, '/api/emplacements', { genre: 'besoin', ...o });
const service = (o) => post(prep, '/api/demandes', { ...o });

await compte({ type_compte: 'accueillant', pseudo: 'Mairie de Bourganeuf', email: 'mairie@bourganeuf.exemple',
  nature: 'mairie', organisation: 'Mairie de Bourganeuf', commune: 'Bourganeuf' });
await recherche({ titre: 'Un boulanger le mercredi matin', commune: 'Bourganeuf', code_insee: '23030',
  latitude: 45.9531, longitude: 1.7550, activites_souhaitees: ['boulangerie'],
  plages: [{ jour: 'mercredi', debut: '08:00', fin: '12:00' }] });
await compte({ type_compte: 'accueillant', pseudo: 'Camping du Lac', email: 'accueil@camping.exemple',
  nature: 'camping', organisation: 'Camping du Lac de Courtille', commune: 'Guéret' });
await post(prep, '/api/emplacements', { genre: 'emplacement', titre: 'Pizzas le vendredi soir, l’été',
  commune: 'Guéret', code_insee: '23096', adresse: 'Lac de Courtille, Guéret', latitude: 46.1793, longitude: 1.8417,
  activites_souhaitees: ['food_truck'], electricite: true, eau: true, gratuit: true,
  plages: [{ jour: 'vendredi', debut: '18:00', fin: '22:00' }] });

await compte({ type_compte: 'commercant', pseudo: 'Le Fournil Roulant', email: 'fournil@exemple.fr',
  organisation: 'Le Fournil Roulant', categories: ['alimentaire'] });
await service({ titre: 'Pain au levain et viennoiseries', categorie: 'alimentaire', activite: 'boulangerie',
  latitude: 45.9575, longitude: 1.7525, commune: 'Bourganeuf',
  zones: [{ genre: 'cercle', lat: 45.9575, lon: 1.7525, rayon_km: 20 }],
  plages: [{ jour: 'mercredi', debut: '07:00', fin: '12:00' }, { jour: 'samedi', debut: '07:00', fin: '12:00' }] });
await compte({ type_compte: 'commercant', pseudo: 'Coiff’Mobile', email: 'coiff@exemple.fr',
  organisation: 'Coiff’Mobile', categories: ['services'] });
await service({ titre: 'Coiffure à domicile et en camion', categorie: 'services', activite: 'coiffure',
  latitude: 45.83, longitude: 1.26, commune: 'Limoges',
  zones: [{ genre: 'ville', code_insee: '87085' }],
  plages: [{ jour: 'lundi', debut: '09:00', fin: '17:00' }] });
await compte({ type_compte: 'commercant', pseudo: 'France services itinérant', email: 'fs@exemple.fr',
  organisation: 'Bus France services', categories: ['administratif'] });
await service({ titre: 'Démarches administratives', categorie: 'administratif', activite: 'france_services',
  latitude: 46.05, longitude: 2.05, commune: 'Ahun', zones: [] });
cli('promouvoir "France services itinérant" administrateur');
await prep.close();

// ------------------------------------------------------------------
// 1. Le visiteur : la carte
// ------------------------------------------------------------------
const v = await page();
await cadrer(v, 2);
await capture(v, '01-carte-visiteur', { attente: 2500 });
await ouvrirRepere(v, 'Pain au levain et viennoiseries');
await capture(v, '02-fiche-visiteur');
await v.close();

// ------------------------------------------------------------------
// 2. La mairie s'inscrit et publie sa recherche
// ------------------------------------------------------------------
const m = await page();
await m.click('#bouton-compte');
await m.click('text=Créer un compte');
await m.fill('label:has-text("Nom affiché") input', 'Mairie de Guéret');
await m.fill('label:has-text("Adresse électronique") input', 'mairie@gueret.exemple');
await m.fill('label:has-text("Mot de passe") input', MDP);
await m.fill('label:has-text("Nom de l’organisation") input', 'Mairie de Guéret');
await m.fill('input[placeholder="Nom de votre commune"]', 'Guéret');
await m.click('label:has-text("Commune") button:has-text("Chercher")');
await m.waitForTimeout(700);
await m.locator('.resultats-position button').first().click();
await m.check('text=J’ai compris');
await capture(m, '03-inscription-mairie');
await m.click('button:has-text("Créer mon compte")');
await m.waitForTimeout(1000);
await m.click('#bouton-publier');
await m.fill('label:has-text("Titre") input', 'Un food truck le mardi midi');
await m.check('fieldset:has-text("Services recherchés") label.case:has-text("Alimentaire") input');
await m.click('fieldset:has-text("Créneaux souhaités") button:has-text("Ajouter une plage")');
const pl = m.locator('fieldset:has-text("Créneaux souhaités") .plage').first();
await pl.locator('select').selectOption('mardi');
await pl.locator('input').nth(0).fill('11:00');
await pl.locator('input').nth(1).fill('14:00');
await m.fill('input[placeholder="Adresse ou commune"]', 'Place Bonnyaud, Guéret');
await m.click('fieldset:has-text("Où ?") button:has-text("Chercher")');
await m.waitForTimeout(2000);
await m.locator('.resultats-position button').first().click();
await m.waitForTimeout(500);
await capture(m, '04-publier-recherche');
await m.click('form button[type=submit]');
await m.waitForTimeout(1500);
await capture(m, '05-recherche-publiee');

// ------------------------------------------------------------------
// 3. Le service ambulant : zones, disponibilités, historique
// ------------------------------------------------------------------
const c = await page();
await post(c, '/api/comptes', { type_compte: 'commercant', pseudo: 'Pizza Nomade', email: 'pizza@exemple.fr',
  mot_de_passe: MDP, organisation: 'Pizza Nomade', categories: ['alimentaire'], conditions_acceptees: true });
await c.reload(); await c.waitForTimeout(900);
await c.click('#bouton-publier');
await c.fill('label:has-text("Titre") input', 'Pizzas au feu de bois');
await c.selectOption('label:has-text("Activité") select >> nth=0', 'food_truck').catch(() => {});
await c.fill('input[placeholder="Adresse ou commune"]', 'Sainte-Feyre');
await c.click('fieldset:has-text("Où êtes-vous installé") button:has-text("Chercher")');
await c.waitForTimeout(2000);
await c.locator('.resultats-position button').first().click();
await c.waitForTimeout(500);
await c.click('button:has-text("+ Un cercle")');
await c.fill('.outil-zone input[type=number]', '15');
await c.waitForTimeout(900);
await capture(c, '06-zone-cercle');
await c.click('button:has-text("Ajouter ce cercle")');
await c.waitForTimeout(800);
await c.click('button:has-text("+ Une ville")');
await c.fill('.outil-zone input[type=search]', 'Bourganeuf');
await c.click('.outil-zone button:has-text("Chercher")');
await c.waitForTimeout(800);
await c.locator('.outil-zone .resultats-position button').first().click();
await c.waitForTimeout(800);
await c.click('button:has-text("+ Dessiner une zone")');
await c.waitForTimeout(300);
const b = await c.locator('#carte').boundingBox();
const cx = b.x + b.width * 0.6, cy = b.y + b.height * 0.5;
await c.mouse.move(cx + 190, cy); await c.mouse.down();
for (let a = 0; a <= 2 * Math.PI + 0.01; a += 0.1) await c.mouse.move(cx + 190 * Math.cos(a), cy + 150 * Math.sin(a) + 20 * Math.sin(3 * a));
await c.mouse.up();
await c.waitForTimeout(1200);
await capture(c, '07-zones-saisies');
await c.click('fieldset:has-text("Mes disponibilités") button:has-text("Ajouter une plage")');
const dp = c.locator('fieldset:has-text("Mes disponibilités") .plage').first();
await dp.locator('select').selectOption('mardi');
await dp.locator('input').nth(0).fill('10:00');
await dp.locator('input').nth(1).fill('15:00');
await c.locator('fieldset:has-text("Mes disponibilités")').scrollIntoViewIfNeeded();
await capture(c, '08-disponibilites');
await c.click('form button[type=submit]');
await c.waitForTimeout(2000);
await capture(c, '09-historique');
await c.locator('#contenu-panneau details:has(summary:has-text("villes"))').first().evaluate(d => { d.open = true; });
await c.locator('#contenu-panneau button:has-text("Voir la zone")').first().click();
await c.waitForTimeout(900);
await capture(c, '10-historique-villes');

// ------------------------------------------------------------------
// 4. La mairie est prévenue ; sa carte ne montre que ce qui vient chez elle
// ------------------------------------------------------------------
await m.reload(); await m.waitForTimeout(1200);
await cadrer(m, 2);
await m.click('#bouton-notifications');
await m.waitForTimeout(800);
await capture(m, '11-notifications');
await m.click('button:has-text("Voir le service et sa zone")');
await m.waitForTimeout(1400);
await capture(m, '12-fiche-service');
await m.click('#fermer-panneau');
await cadrer(m, 2);
await capture(m, '13-carte-mairie', { attente: 2000 });

// ------------------------------------------------------------------
// 5. Les filtres
// ------------------------------------------------------------------
const f = await page();
await cadrer(f, 2);
await f.selectOption('#filtre-categorie', 'alimentaire');
await f.click('#bouton-filtres');
await f.selectOption('#panneau-filtres label:has-text("Jour") select', 'mardi');
await f.selectOption('#panneau-filtres label:has-text("Électricité") select', 'oui_inconnu');
await capture(f, '14-filtres');
await f.close();

// ------------------------------------------------------------------
// 6. La console de l'administrateur
// ------------------------------------------------------------------
const a = await page(1280, 1000);
await connecter(a, 'fs@exemple.fr');
await a.click('#bouton-console');
await a.waitForTimeout(1000);
await capture(a, '15-console');
await a.evaluate(() => {
  const h = [...document.querySelectorAll('#contenu-panneau h3')].find(x => x.textContent.includes('Tableau des droits'));
  document.getElementById('panneau').scrollTop = h.offsetTop - 10;
});
await capture(a, '16-tableau-droits');
await a.close();

// ------------------------------------------------------------------
// 7. Sur téléphone
// ------------------------------------------------------------------
const t = await page(390, 844, true);
await cadrer(t, 3);
await capture(t, '17-mobile-carte', { attente: 2000 });
await ouvrirRepere(t, 'Un boulanger le mercredi matin');
await capture(t, '18-mobile-fiche');
await t.click('#fermer-panneau');
await t.click('#bouton-filtres');
await capture(t, '19-mobile-filtres', { attente: 500 });
await t.close();

await c.close(); await m.close();

// ------------------------------------------------------------------
// Le PDF
// ------------------------------------------------------------------
const doc = await (await nav.newContext()).newPage();
await doc.goto('file://' + path.join(SORTIE, 'notice.html'));
await doc.waitForTimeout(500);
await doc.pdf({ path: path.join(SORTIE, 'notice-services-ambulants.pdf'), format: 'A4',
  printBackground: true, margin: { top: '16mm', bottom: '18mm', left: '15mm', right: '15mm' },
  displayHeaderFooter: true, headerTemplate: '<span></span>',
  footerTemplate: '<div style="font:8px system-ui;color:#888;width:100%;text-align:center">'
    + 'Services ambulants (nom provisoire) — spécification fonctionnelle et notice — page '
    + '<span class="pageNumber"></span> / <span class="totalPages"></span></div>' });
console.log('PDF écrit');
console.log('erreurs', JSON.stringify(erreurs));
await nav.close();
