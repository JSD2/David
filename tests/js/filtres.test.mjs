// Les filtres de la carte, éprouvés hors de la page.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const F = require('../../ambulants/web/filtres.js');
const ACT = { food_truck: { categorie: 'alimentaire' }, boulangerie: { categorie: 'alimentaire' }, coiffure: { categorie: 'services' } };
const MAINTENANT = Date.parse('2026-10-22T12:00:00Z');

const service = (o = {}) => ({ sens: 'demande', categorie: 'alimentaire', activite: 'food_truck',
  plages: [{ jour: 'mardi', debut: '11:00', fin: '14:00' }], date: '2026-10-20T10:00:00+00:00', ...o });
const recherche = (o = {}) => ({ sens: 'emplacement', activites: ['alimentaire'], exclues: [], plages: [],
  electricite: null, eau: true, gratuit: false, verifie: false, date: '2026-07-01T10:00:00+00:00', ...o });
const passe = (a, f) => F.correspond(a, { ...F.vides(), ...f }, ACT, MAINTENANT);

test('sans filtre, tout passe', () => {
  assert.ok(passe(service(), {}));
  assert.ok(passe(recherche(), {}));
});

test('activité précise', () => {
  assert.ok(passe(service(), { categorie: 'alimentaire', activite: 'food_truck' }));
  assert.ok(!passe(service(), { categorie: 'alimentaire', activite: 'boulangerie' }));
  // Une recherche « alimentaire » accepte la boulangerie ; une recherche
  // sans activité les accepte toutes ; une exclusion écarte.
  assert.ok(passe(recherche(), { categorie: 'alimentaire', activite: 'boulangerie' }));
  assert.ok(passe(recherche({ activites: [] }), { categorie: 'services', activite: 'coiffure' }));
  assert.ok(!passe(recherche({ activites: [], exclues: ['coiffure'] }), { categorie: 'services', activite: 'coiffure' }));
  assert.ok(!passe(recherche(), { categorie: 'services' }));
});

test('jour et heure, et les annonces sans horaires', () => {
  assert.ok(passe(service(), { jour: 'mardi' }));
  assert.ok(!passe(service(), { jour: 'jeudi' }));
  assert.ok(passe(service(), { jour: 'mardi', debut: '13:00', fin: '18:00' }));
  assert.ok(!passe(service(), { jour: 'mardi', debut: '14:00', fin: '18:00' }));
  // Non renseigné n'est pas « jamais » : inclus, sauf si on le décoche.
  assert.ok(passe(recherche(), { jour: 'lundi' }));
  assert.ok(!passe(recherche(), { jour: 'lundi', sansHoraires: false }));
  // Les annonces d'avant les plages : leurs jours.
  assert.ok(passe(recherche({ jours: ['lundi'] }), { jour: 'lundi', sansHoraires: false }));
  assert.ok(!passe(recherche({ jours: ['lundi'] }), { jour: 'mardi' }));
});

test('équipements : non renseigné n’est pas « non »', () => {
  assert.ok(passe(recherche(), { eau: 'oui' }));
  assert.ok(!passe(recherche(), { electricite: 'oui' }));
  assert.ok(passe(recherche(), { electricite: 'oui_inconnu' }));
  assert.ok(!passe(recherche(), { gratuit: 'oui_inconnu' })); // « non » dit : écarté
  assert.ok(passe(service(), { electricite: 'oui', gratuit: 'oui' })); // un service n'est pas un lieu
});

test('confiance et fraîcheur', () => {
  assert.ok(!passe(recherche(), { mairiesVerifiees: true }));
  assert.ok(passe(recherche({ verifie: true }), { mairiesVerifiees: true }));
  assert.ok(passe(service(), { mairiesVerifiees: true }));
  assert.ok(passe(service(), { ageJours: 7 }));
  assert.ok(!passe(recherche(), { ageJours: 30 }));
  assert.ok(!passe(recherche({ date: undefined }), { ageJours: 30 }));
});

test('pastilles et leur remise à zéro', () => {
  const p = F.actifs({ ...F.vides(), jour: 'mardi', debut: '08:00', eau: 'oui_inconnu', ageJours: 7 }, x => x);
  assert.deepEqual(p.map(x => x.texte), ['mardi 08:00–…', 'Eau (ou non renseigné)', 'Moins de 7 jours']);
  assert.deepEqual(p[0].remise, { jour: '', debut: '', fin: '', sansHoraires: true });
});
