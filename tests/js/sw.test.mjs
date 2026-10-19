// Le tri du service worker : ce qui est gardé, ce qui ne l'est jamais.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { estUneTuileIgn, aGarder } = require('../../ambulants/web/sw.js');
const ICI = 'https://exemple.fr';

test('les tuiles IGN plan et satellite sont reconnues', () => {
  const base = 'https://data.geopf.fr/wmts?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile';
  assert.ok(estUneTuileIgn(`${base}&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal`));
  assert.ok(estUneTuileIgn(`${base}&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal`));
  assert.ok(!estUneTuileIgn(`${base}&LAYER=AUTRE.COUCHE&STYLE=normal`));
  assert.ok(!estUneTuileIgn('https://data.geopf.fr/geocodage/search?q=x'));
});

test('ce qui regarde un compte n’est jamais gardé', () => {
  for (const p of ['/api/session', '/api/moi', '/api/moderation/accueillants', '/api/admin/droits']) {
    assert.equal(aGarder(ICI + p, 'GET'), false, p);
  }
  assert.equal(aGarder(ICI + '/api/carte', 'POST'), false);
});

test('la page, ses fichiers et la carte le sont', () => {
  for (const p of ['/', '/static/app.js', '/api/carte']) assert.equal(aGarder(ICI + p, 'GET'), true, p);
});
