// La page de la carte : une seule carte pour les deux parties.
//
// Les annonces, les catégories et les listes arrivent DANS la page (balise
// « donnees ») : la carte se dessine sans attendre un second aller et
// retour. La session et les droits, eux, se lisent ensuite — ils dépendent
// de qui regarde.
//
// Tout ce qui vient d'un utilisateur est posé en texte (`textContent`),
// jamais en HTML : un titre d'annonce ne peut pas devenir du code.
'use strict';

(function () {
  const D = JSON.parse(document.getElementById('donnees').textContent);
  const CATEGORIES = D.categories;
  const CAT = Object.fromEntries(CATEGORIES.map(c => [c.cle, c]));
  const ACTIVITE = {};
  CATEGORIES.forEach(c => c.activites.forEach(a => { ACTIVITE[a.cle] = { ...a, categorie: c.cle }; }));
  const GEOCODAGE = 'https://data.geopf.fr/geocodage/search';

  const etat = {
    sens: 'tout',
    categorie: '',
    compte: null,
    droits: null,
    annonces: D.carte.annonces,
    placement: null, // fonction appelée au prochain clic sur la carte
  };

  // ------------------------------------------------------------------
  // Outils
  // ------------------------------------------------------------------

  /** Un élément, ses attributs, ses enfants (textes ou éléments). */
  function el(tag, attrs, ...enfants) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'onclick' || k === 'onchange' || k === 'onsubmit' || k === 'oninput') e[k] = v;
      else if (k === 'class') e.className = v;
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of enfants.flat()) {
      if (c === null || c === undefined || c === false) continue;
      e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return e;
  }

  async function api(chemin, corps) {
    const options = corps === undefined ? { credentials: 'same-origin' } : {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps),
    };
    const r = await fetch(chemin, options);
    let lu = null;
    try { lu = await r.json(); } catch (_) { /* corps vide */ }
    if (!r.ok) throw new Error((lu && lu.erreur) || `Erreur ${r.status}`);
    return lu;
  }

  function permis(cle) {
    if (!etat.droits) return false;
    const f = etat.droits.fonctionnalites.find(x => x.cle === cle);
    return !!(f && f.permis);
  }

  /** Oui / non / non renseigné : `null` n'est jamais « non ». */
  function triEtat(v) {
    if (v === true) return 'Oui';
    if (v === false) return 'Non';
    return el('span', { class: 'inconnu' }, 'non renseigné');
  }

  function ouInconnu(v, suffixe) {
    if (v === null || v === undefined || v === '') return el('span', { class: 'inconnu' }, 'non renseigné');
    return suffixe ? `${v} ${suffixe}` : String(v);
  }

  function libelleActivite(cle) {
    if (CAT[cle]) return CAT[cle].libelle;
    if (ACTIVITE[cle]) return ACTIVITE[cle].libelle;
    return cle;
  }

  /** « mardi 08:00–13:00, jeudi 18:00–22:00 » ; rien donné : non renseigné. */
  function textePlages(plages) {
    if (!plages || !plages.length) return el('span', { class: 'inconnu' }, 'non renseignés');
    return plages.map(p => `${p.jour} ${p.debut}–${p.fin}`).join(', ');
  }

  function jours(liste) {
    return liste && liste.length ? liste.join(', ') : el('span', { class: 'inconnu' }, 'non renseignés');
  }

  // ------------------------------------------------------------------
  // La carte
  // ------------------------------------------------------------------

  const carte = L.map('carte', { zoomControl: true }).setView([46.6, 2.4], 6);
  function wmts(couche, format) {
    return 'https://data.geopf.fr/wmts?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile'
      + `&LAYER=${couche}&STYLE=normal&FORMAT=image/${format}`
      + '&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}';
  }
  const credit = '&copy; <a href="https://www.ign.fr/">IGN</a> — Géoplateforme';
  const fonds = {
    plan: L.tileLayer(wmts('GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2', 'png'), { maxZoom: 19, attribution: credit }),
    satellite: L.tileLayer(wmts('ORTHOIMAGERY.ORTHOPHOTOS', 'jpeg'), { maxZoom: 19, attribution: credit }),
  };
  fonds.plan.addTo(carte);
  document.querySelectorAll('#fonds button').forEach(b => b.addEventListener('click', () => {
    Object.values(fonds).forEach(f => carte.removeLayer(f));
    fonds[b.dataset.fond].addTo(carte);
    document.querySelectorAll('#fonds button').forEach(x => x.setAttribute('aria-checked', String(x === b)));
  }));

  const calque = L.layerGroup().addTo(carte);
  // Les zones d'action montrées (fiche, historique, saisie).
  const calqueZones = L.layerGroup().addTo(carte);
  let cercle = null;

  function classeDe(a) {
    if (a.sens === 'demande') return 'demande';
    return a.genre === 'besoin' ? 'besoin' : 'emplacement';
  }

  function visible(a) {
    if (etat.sens !== 'tout' && a.sens !== etat.sens) return false;
    if (etat.categorie) {
      if (a.sens === 'demande') return a.categorie === etat.categorie;
      // Un emplacement sans activité souhaitée est ouvert à toutes.
      if (!a.activites.length) return true;
      return a.activites.some(x => x === etat.categorie || (ACTIVITE[x] && ACTIVITE[x].categorie === etat.categorie));
    }
    return true;
  }

  function dessiner() {
    calque.clearLayers();
    let n = 0;
    for (const a of etat.annonces) {
      if (!visible(a)) continue;
      n += 1;
      const icone = L.divIcon({ className: 'repere', html: `<i class="pastille ${classeDe(a)}"></i>`, iconSize: [22, 22] });
      const m = L.marker([a.lat, a.lon], { icon: icone, title: a.titre, keyboard: true });
      m.on('click', () => ouvrirFiche(a.id));
      m.addTo(calque);
    }
    document.getElementById('compte-annonces').textContent = `${n} annonce${n > 1 ? 's' : ''} affichée${n > 1 ? 's' : ''}`;
  }

  async function rechargerCarte() {
    try {
      const r = await api('/api/carte');
      etat.annonces = r.annonces;
      dessiner();
    } catch (_) { /* la carte déjà dessinée reste */ }
  }

  document.querySelectorAll('#sens button').forEach(b => b.addEventListener('click', () => {
    etat.sens = b.dataset.sens;
    document.querySelectorAll('#sens button').forEach(x => x.setAttribute('aria-checked', String(x === b)));
    dessiner();
  }));

  const selectCat = document.getElementById('filtre-categorie');
  CATEGORIES.forEach(c => selectCat.append(el('option', { value: c.cle }, c.libelle)));
  selectCat.addEventListener('change', () => { etat.categorie = selectCat.value; dessiner(); });

  carte.on('click', (e) => {
    if (etat.placement) etat.placement(e.latlng);
  });

  // ------------------------------------------------------------------
  // Recherche d'adresse : la Base adresse nationale, servie par la
  // Géoplateforme. La requête part du navigateur, pas de notre serveur.
  // ------------------------------------------------------------------

  async function geocoder(texte) {
    const u = `${GEOCODAGE}?q=${encodeURIComponent(texte)}&limit=6`;
    const r = await fetch(u);
    if (!r.ok) throw new Error('La recherche d’adresse ne répond pas.');
    const g = await r.json();
    return (g.features || []).map(f => ({
      libelle: f.properties.label, commune: f.properties.city, insee: f.properties.citycode,
      type: f.properties.type, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0],
    }));
  }

  const recherche = document.getElementById('recherche');
  const resultats = document.getElementById('recherche-resultats');
  recherche.addEventListener('submit', async (e) => {
    e.preventDefault();
    const texte = document.getElementById('recherche-texte').value.trim();
    if (texte.length < 3) return;
    resultats.replaceChildren();
    try {
      const trouves = await geocoder(texte);
      if (!trouves.length) resultats.append(el('li', {}, el('span', { class: 'aide' }, 'Rien trouvé.')));
      trouves.forEach(t => resultats.append(el('li', {}, el('button', { type: 'button', onclick: () => {
        carte.setView([t.lat, t.lon], t.type === 'municipality' ? 12 : 16);
        resultats.hidden = true;
      } }, t.libelle))));
    } catch (err) {
      resultats.append(el('li', {}, el('span', { class: 'erreur' }, err.message)));
    }
    resultats.hidden = false;
  });

  // ------------------------------------------------------------------
  // Le panneau
  // ------------------------------------------------------------------

  const panneau = document.getElementById('panneau');
  const contenu = document.getElementById('contenu-panneau');
  function ouvrir(...enfants) {
    etat.placement = null;
    calqueZones.clearLayers();
    if (cercle) { carte.removeLayer(cercle); cercle = null; }
    // replaceChildren écrirait « null » en toutes lettres pour un bloc absent.
    contenu.replaceChildren(...enfants.flat().filter(x => x !== null && x !== undefined && x !== false));
    panneau.hidden = false;
    panneau.scrollTop = 0;
    carte.invalidateSize();
  }
  function fermer() {
    etat.placement = null;
    calqueZones.clearLayers();
    panneau.hidden = true;
    carte.invalidateSize();
  }
  document.getElementById('fermer-panneau').addEventListener('click', fermer);

  function avertissementLegal(texte) {
    return el('p', { class: 'avertissement', role: 'note' }, texte || D.avertissement_legal);
  }

  // ------------------------------------------------------------------
  // La fiche
  // ------------------------------------------------------------------

  async function ouvrirFiche(id, bandeau) {
    let f;
    try { f = await api(`/api/annonces/${id}`); } catch (err) {
      ouvrir(el('p', { class: 'erreur' }, err.message)); return;
    }
    const auteur = f.auteur || {};
    const badge = f.sens === 'emplacement'
      ? (auteur.verifie ? el('span', { class: 'badge ok' }, 'Accueillant vérifié') : null)
      : (auteur.entreprise_verifiee ? el('span', { class: 'badge ok' }, 'Entreprise vérifiée') : null);
    const titreSens = f.sens === 'demande' ? 'Service ambulant'
      : (f.genre === 'besoin' ? 'Recherche d’un service (sans lieu fixé)' : 'Recherche d’un service, emplacement proposé');

    const faits = el('dl', { class: 'faits' });
    const fait = (dt, dd) => faits.append(el('dt', {}, dt), el('dd', {}, dd));
    fait('Commune', ouInconnu(f.commune));
    // Les annonces d'avant les plages horaires n'ont que des jours.
    if (!f.plages.length && f.jours.length) fait('Jours', jours(f.jours));
    if (f.sens === 'demande') {
      fait('Activité', `${libelleActivite(f.categorie)} — ${libelleActivite(f.activite)}`);
      fait('Disponibilités', textePlages(f.plages));
      fait('Zones d’action', f.zones.length
        ? el('span', {}, f.zones.map(z => `${z.libelle} (${z.nombre_communes} commune${z.nombre_communes > 1 ? 's' : ''})`).join(', '), ' ',
          el('button', { type: 'button', onclick: () => afficherZones(f.zones) }, 'Voir sur la carte'))
        : ouInconnu(f.rayon_km, 'km autour du point'));
      fait('Électricité', triEtat(f.besoin_electricite));
      fait('Eau', triEtat(f.besoin_eau));
      fait('Surface', ouInconnu(f.surface_m2, 'm²'));
      const champs = (CAT[f.categorie] || { champs: [] }).champs;
      champs.forEach(c => {
        const v = f.champs_activite[c.cle];
        fait(c.libelle, c.genre === 'oui_non' ? triEtat(v) : ouInconnu(v));
      });
    } else {
      if (f.genre === 'emplacement') fait('Adresse', ouInconnu(f.adresse));
      fait('Créneaux souhaités', textePlages(f.plages));
      if (f.creneaux) fait('Précisions horaires', f.creneaux);
      fait('Électricité', triEtat(f.electricite));
      fait('Eau', triEtat(f.eau));
      fait('Redevance', ouInconnu(f.redevance));
      fait('Services recherchés', f.activites_souhaitees.length ? f.activites_souhaitees.map(libelleActivite).join(', ') : 'tous');
      if (f.activites_exclues.length) fait('Services exclus', f.activites_exclues.map(libelleActivite).join(', '));
      if (f.conditions) fait('Conditions', f.conditions);
    }

    const blocs = [
      bandeau ? el('p', { class: 'info', role: 'status' }, bandeau) : null,
      el('h2', {}, f.titre),
      el('p', { class: 'sous-titre' }, titreSens, ' · ', auteur.organisation || auteur.pseudo || '', ' ', badge),
      f.etat !== 'publie' ? el('p', { class: 'avertissement' }, f.etat === 'masque'
        ? `Annonce masquée par la modération : ${f.motif_masquage || ''}` : 'Annonce retirée par son auteur.') : null,
      f.description ? el('p', {}, f.description) : null,
      faits,
      ...f.avertissements_activites.map(t => avertissementLegal(t)),
      avertissementLegal(),
      el('p', { class: 'info' }, 'La candidature, la messagerie et l’échange de coordonnées arrivent dans la prochaine version.'),
    ];
    if (etat.compte && auteur.identifiant === etat.compte.identifiant && f.etat === 'publie' && permis('retirer_annonce')) {
      blocs.push(el('button', { type: 'button', class: 'danger', onclick: async () => {
        if (!confirm('Retirer cette annonce de la carte ?')) return;
        try { await api(`/api/annonces/${f.id}/retirer`, {}); await rechargerCarte(); fermer(); } catch (err) { alert(err.message); }
      } }, 'Retirer mon annonce'));
    }
    if (permis('mod_annonces')) blocs.push(blocModeration(f));
    ouvrir(...blocs);
    if (f.sens === 'demande' && f.zones.length) afficherZones(f.zones);
    else carte.panTo([f.lat, f.lon]);
  }

  function blocModeration(f) {
    const motif = el('input', { type: 'text', placeholder: 'Motif (obligatoire pour masquer)' });
    const message = el('p', { class: 'aide' });
    const agir = async (action) => {
      try {
        await api(`/api/moderation/annonces/${f.id}`, { action, motif: motif.value });
        await rechargerCarte();
        ouvrirFiche(f.id);
      } catch (err) { message.textContent = err.message; message.className = 'erreur'; }
    };
    return el('div', { class: 'carte-liste' }, el('h3', {}, 'Modération'),
      f.etat === 'masque'
        ? el('button', { type: 'button', onclick: () => agir('reafficher') }, 'Réafficher')
        : el('div', { class: 'formulaire' }, motif, el('button', { type: 'button', class: 'danger', onclick: () => agir('masquer') }, 'Masquer')),
      message);
  }

  // ------------------------------------------------------------------
  // Session et compte
  // ------------------------------------------------------------------

  async function lireSession() {
    try {
      const s = await api('/api/session');
      appliquerSession(s);
    } catch (_) { /* sans session lisible, on reste visiteur */ }
  }

  function appliquerSession(s) {
    etat.compte = s.compte;
    etat.droits = s.droits;
    const bc = document.getElementById('bouton-compte');
    bc.textContent = s.compte ? s.compte.pseudo : 'Se connecter';
    document.getElementById('bouton-publier').hidden = !(permis('publier_emplacement') || permis('publier_demande')
      || (s.compte && s.compte.type_compte === 'accueillant'));
    document.getElementById('bouton-console').hidden = !(permis('mod_verifier_accueillants') || permis('mod_annonces') || permis('adm_droits'));
    lireNotifications();
    // Une ligne « écran » fermée retire son élément.
    document.querySelectorAll('[data-droit]').forEach(n => {
      n.hidden = !permis(n.dataset.droit);
    });
  }

  document.getElementById('bouton-compte').addEventListener('click', () => {
    if (etat.compte) ouvrirMonCompte(); else ouvrirConnexion('connexion');
  });

  function champ(libelle, controle, aide) {
    return el('label', {}, libelle, controle, aide ? el('span', { class: 'aide' }, aide) : null);
  }

  function ouvrirConnexion(onglet) {
    const message = el('p', { class: 'erreur', role: 'alert' });
    const onglets = el('div', { class: 'onglets', role: 'tablist' },
      el('button', { type: 'button', role: 'tab', 'aria-selected': String(onglet === 'connexion'), onclick: () => ouvrirConnexion('connexion') }, 'Se connecter'),
      permis('inscription') ? el('button', { type: 'button', role: 'tab', 'aria-selected': String(onglet === 'inscription'), onclick: () => ouvrirConnexion('inscription') }, 'Créer un compte') : null);

    if (onglet === 'connexion') {
      const email = el('input', { type: 'email', required: true, autocomplete: 'email' });
      const mdp = el('input', { type: 'password', required: true, autocomplete: 'current-password' });
      const f = el('form', { class: 'formulaire', onsubmit: async (e) => {
        e.preventDefault();
        try {
          appliquerSession(await api('/api/session', { email: email.value, mot_de_passe: mdp.value }));
          fermer();
        } catch (err) { message.textContent = err.message; }
      } }, champ('Adresse électronique', email), champ('Mot de passe', mdp), message,
      el('button', { type: 'submit', class: 'principal' }, 'Se connecter'));
      ouvrir(el('h2', {}, 'Mon compte'), onglets, f);
      return;
    }

    const type = { valeur: 'accueillant' };
    const blocType = el('div');
    const pseudo = el('input', { type: 'text', required: true, minlength: '2', maxlength: '40' });
    const email = el('input', { type: 'email', required: true, autocomplete: 'email' });
    const mdp = el('input', { type: 'password', required: true, minlength: '12', autocomplete: 'new-password' });
    const nature = el('select', {}, ...D.natures.map(n => el('option', { value: n.cle }, n.libelle)));
    const organisation = el('input', { type: 'text', maxlength: '120', placeholder: 'Mairie de Saint-Julien' });
    const commune = el('input', { type: 'text', maxlength: '120' });
    const siret = el('input', { type: 'text', inputmode: 'numeric', maxlength: '17', placeholder: '14 chiffres' });
    const cases = CATEGORIES.map(c => el('input', { type: 'checkbox', value: c.cle }));
    const presentation = el('textarea', { rows: '3', maxlength: '2000' });
    const conditions = el('input', { type: 'checkbox', required: true });

    function blocSelonType() {
      if (type.valeur === 'accueillant') {
        blocType.replaceChildren(
          champ('Vous êtes', nature), champ('Nom de l’organisation', organisation),
          champ('Commune', commune),
          el('p', { class: 'info' }, 'Vous pourrez publier dès votre inscription. La modération peut ensuite '
            + 'vérifier votre compte (badge « Accueillant vérifié ») : une adresse électronique officielle, '
            + 'celle de l’Annuaire de l’administration, l’y aide.'));
      } else {
        blocType.replaceChildren(
          champ('Nom de l’entreprise (facultatif)', organisation),
          champ('SIRET (facultatif)', siret, 'Déclaré seulement : la vérification par l’annuaire des entreprises viendra plus tard.'),
          el('fieldset', {}, el('legend', {}, 'Vos activités'),
            el('div', { class: 'cases' }, ...CATEGORIES.map((c, i) => el('label', { class: 'case' }, cases[i], c.libelle)))));
      }
    }
    const choixType = el('fieldset', {}, el('legend', {}, 'Je suis'),
      el('div', { class: 'cases' }, ...[['accueillant', 'Un accueillant (mairie, camping, entreprise…)'], ['commercant', 'Un service ambulant']].map(([v, l]) =>
        el('label', { class: 'case' }, el('input', { type: 'radio', name: 'type', value: v, checked: v === type.valeur,
          onchange: () => { type.valeur = v; blocSelonType(); } }), l))));
    blocSelonType();

    const f = el('form', { class: 'formulaire', onsubmit: async (e) => {
      e.preventDefault();
      try {
        appliquerSession(await api('/api/comptes', {
          type_compte: type.valeur, pseudo: pseudo.value, email: email.value, mot_de_passe: mdp.value,
          nature: type.valeur === 'accueillant' ? nature.value : '', organisation: organisation.value,
          commune: commune.value, siret: type.valeur === 'commercant' ? siret.value : '',
          categories: cases.filter(c => c.checked).map(c => c.value),
          presentation: presentation.value, conditions_acceptees: conditions.checked,
        }));
        ouvrirMonCompte();
      } catch (err) { message.textContent = err.message; }
    } }, choixType, champ('Nom affiché', pseudo), champ('Adresse électronique', email, 'Jamais affichée publiquement.'),
    champ('Mot de passe', mdp, 'Au moins 12 caractères.'), blocType, champ('Présentation (facultatif)', presentation),
    el('label', { class: 'case' }, conditions, 'J’ai compris que ce site aide à se trouver et ne délivre aucune autorisation.'),
    message, el('button', { type: 'submit', class: 'principal' }, 'Créer mon compte'));
    ouvrir(el('h2', {}, 'Mon compte'), onglets, f);
  }

  async function ouvrirMonCompte(bandeau) {
    let moi;
    let historique = null;
    try {
      moi = await api('/api/moi');
      if (permis('historique_demandes')) historique = (await api('/api/moi/historique')).demandes;
    } catch (err) { ouvrir(el('p', { class: 'erreur' }, err.message)); return; }
    const c = moi.compte;
    let statut = null;
    if (c.type_compte === 'accueillant') {
      statut = c.verification === 'verifie' ? el('span', { class: 'badge ok' }, 'Vérifié')
        : c.verification === 'refuse' ? el('span', { class: 'badge' }, `Vérification refusée : ${c.verification_motif || ''}`)
          : el('span', { class: 'badge' }, 'Pas encore vérifié');
    }
    const annonces = historique ? blocHistorique(historique) : moi.annonces.length ? moi.annonces.map(a => el('div', { class: 'carte-liste' },
      el('strong', {}, a.titre), ' ', el('span', { class: 'badge' }, { publie: 'publiée', retire: 'retirée', masque: 'masquée' }[a.etat] || a.etat),
      el('div', {}, el('button', { type: 'button', onclick: () => ouvrirFiche(a.id) }, 'Voir la fiche'))))
      : [el('p', { class: 'aide' }, 'Aucune annonce pour l’instant.')];

    const mdp = el('input', { type: 'password', autocomplete: 'current-password' });
    const message = el('p', { class: 'erreur' });
    ouvrir(
      bandeau ? el('p', { class: 'info', role: 'status' }, bandeau) : null,
      el('h2', {}, c.pseudo),
      el('p', { class: 'sous-titre' }, c.type_compte === 'accueillant' ? 'Accueillant' : 'Service ambulant',
        c.organisation ? ` · ${c.organisation}` : '', ' ', statut),
      el('dl', { class: 'faits' }, el('dt', {}, 'Adresse'), el('dd', {}, c.email),
        el('dt', {}, 'Rôle'), el('dd', {}, c.role),
        c.type_compte === 'commercant' ? [el('dt', {}, 'SIRET'), el('dd', {}, c.siret ? `${c.siret} (déclaré)` : ouInconnu(null))] : null),
      el('h3', {}, historique ? 'Mes demandes' : 'Mes annonces'), ...annonces,
      el('p', {}, el('button', { type: 'button', onclick: async () => {
        await api('/api/session/fin', {}); appliquerSession(await api('/api/session')); fermer();
      } }, 'Se déconnecter')),
      el('details', {}, el('summary', {}, 'Effacer mon compte'),
        el('p', { class: 'aide' }, 'Le compte, ses annonces et ses sessions sont effacés pour de bon.'),
        el('div', { class: 'formulaire' }, champ('Mot de passe', mdp), message,
          el('button', { type: 'button', class: 'danger', onclick: async () => {
            if (!confirm('Effacer définitivement ce compte ?')) return;
            try { await api('/api/moi/effacer', { mot_de_passe: mdp.value }); appliquerSession(await api('/api/session')); await rechargerCarte(); fermer(); } catch (err) { message.textContent = err.message; }
          } }, 'Effacer'))));
  }

  /** L'historique d'un commerçant : chaque demande, chaque zone, ses
   *  villes, et les mairies prévenues mises en évidence. */
  function blocHistorique(demandes) {
    if (!demandes.length) return [el('p', { class: 'aide' }, 'Aucune demande pour l’instant.')];
    return demandes.map(d => el('div', { class: 'carte-liste' },
      el('strong', {}, d.titre), ' ',
      el('span', { class: 'badge' }, { publie: 'publiée', retire: 'retirée', masque: 'masquée' }[d.etat] || d.etat),
      el('div', { class: 'aide' }, `${libelleActivite(d.activite)} · publiée le ${d.date_creation.slice(0, 10)} · `,
        el('strong', {}, `${d.nombre_mairies_prevenues} mairie${d.nombre_mairies_prevenues > 1 ? 's' : ''} prévenue${d.nombre_mairies_prevenues > 1 ? 's' : ''}`)),
      el('div', { class: 'aide' }, 'Disponibilités : ', textePlages(d.plages)),
      ...d.zones.map(z => el('div', { class: 'zone-historique' },
        el('div', { class: 'cases' }, el('span', {}, el('strong', {}, z.libelle), ` — ${z.nombre_communes} commune${z.nombre_communes > 1 ? 's' : ''}`),
          el('button', { type: 'button', onclick: () => afficherZones([z]) }, 'Voir la zone')),
        el('details', { open: z.communes.some(c => c.prevenues.length) && z.communes.length <= 30 },
          el('summary', {}, z.genre === 'ville' ? 'La ville' : `Les ${z.nombre_communes} villes`),
          el('ul', { class: 'villes' }, ...z.communes.map(c => el('li', { class: c.prevenues.length ? 'prevenue' : '' },
            `${c.nom} (${c.departement})`,
            ...c.prevenues.map(p => el('span', {}, ' ', el('button', { type: 'button', class: 'lien', onclick: () => ouvrirFiche(p.emplacement_id) },
              `Mairie prévenue : ${p.organisation || p.titre}`))))))))),
      el('div', { class: 'cases' },
        el('button', { type: 'button', onclick: () => afficherZones(d.zones) }, 'Voir toutes les zones'),
        el('button', { type: 'button', onclick: () => ouvrirFiche(d.id) }, 'Voir la fiche'))));
  }

  // ------------------------------------------------------------------
  // Notifications : la cloche
  // ------------------------------------------------------------------

  const boutonNotif = document.getElementById('bouton-notifications');
  async function lireNotifications() {
    if (!permis('notifications')) { boutonNotif.hidden = true; return null; }
    try {
      const n = await api('/api/notifications');
      boutonNotif.hidden = false;
      boutonNotif.textContent = n.non_lues ? `Notifications (${n.non_lues})` : 'Notifications';
      boutonNotif.classList.toggle('a-lire', n.non_lues > 0);
      return n;
    } catch (_) { return null; }
  }
  boutonNotif.addEventListener('click', async () => {
    const n = await lireNotifications();
    if (!n) return;
    ouvrir(el('h2', {}, 'Notifications'),
      n.notifications.length ? null : el('p', { class: 'aide' }, 'Rien pour l’instant. Vous serez prévenu ici quand un service ambulant correspondra à l’une de vos recherches.'),
      ...n.notifications.map(x => el('div', { class: 'carte-liste' + (x.lue ? '' : ' non-lue') },
        el('div', { class: 'aide' }, x.date.slice(0, 10)),
        el('strong', {}, x.service || 'Un service'), ` — ${libelleActivite(x.activite || '')}`,
        el('p', {}, `correspond à votre recherche « ${x.titre_recherche || ''} ».`),
        x.creneaux_communs.length ? el('p', { class: 'aide' }, 'Créneaux en commun : ', textePlages(x.creneaux_communs)) : null,
        x.demande_publiee
          ? el('button', { type: 'button', onclick: () => ouvrirFiche(x.demande_id) }, 'Voir le service et sa zone')
          : el('p', { class: 'aide' }, 'Ce service a retiré son annonce.'))));
    if (n.non_lues) {
      try { await api('/api/notifications/lues', {}); } catch (_) { /* compteur inchangé */ }
      lireNotifications();
    }
  });
  // Une mairie qui laisse la page ouverte voit arriver les nouvelles.
  setInterval(() => { if (etat.compte && !document.hidden) lireNotifications(); }, 120000);

  // ------------------------------------------------------------------
  // Publier
  // ------------------------------------------------------------------

  document.getElementById('bouton-publier').addEventListener('click', () => {
    if (!etat.compte) return;
    if (etat.compte.type_compte === 'accueillant') ouvrirPublierEmplacement(); else ouvrirPublierDemande();
  });

  /** Trois états : « non renseigné » est le choix par défaut, pas « non ». */
  function selectTriEtat() {
    return el('select', {}, el('option', { value: '' }, 'Non renseigné'), el('option', { value: 'oui' }, 'Oui'), el('option', { value: 'non' }, 'Non'));
  }
  function valeurTriEtat(s) { return s.value === 'oui' ? true : s.value === 'non' ? false : null; }

  function casesActivites(legende) {
    const cases = CATEGORIES.map(c => el('input', { type: 'checkbox', value: c.cle }));
    const bloc = el('fieldset', {}, el('legend', {}, legende),
      el('div', { class: 'cases' }, ...CATEGORIES.map((c, i) => el('label', { class: 'case' }, cases[i], c.libelle))));
    return { bloc, valeur: () => cases.filter(c => c.checked).map(c => c.value) };
  }

  /** Jours ET horaires : une ligne par plage (jour, de, à). La mairie y
   *  dit les créneaux qu'elle souhaite, le commerçant ceux où il est libre.
   *  Aucune ligne : non renseigné — ce n'est pas « jamais ». */
  function editeurPlages(legende, aide) {
    const lignes = el('div', { class: 'plages' });
    const rangs = [];
    function ajouter(jour, debut, fin) {
      const j = el('select', {}, ...D.jours.map(x => el('option', { value: x, selected: x === jour }, x)));
      const d = el('input', { type: 'time', value: debut || '08:00', step: '900', 'aria-label': 'De' });
      const f = el('input', { type: 'time', value: fin || '12:00', step: '900', 'aria-label': 'À' });
      const rang = { j, d, f };
      const ligne = el('div', { class: 'plage' }, j, el('span', {}, 'de'), d, el('span', {}, 'à'), f,
        el('button', { type: 'button', 'aria-label': 'Retirer cette plage', onclick: () => {
          rangs.splice(rangs.indexOf(rang), 1); ligne.remove();
        } }, '×'));
      rangs.push(rang);
      lignes.append(ligne);
    }
    const bloc = el('fieldset', {}, el('legend', {}, legende),
      aide ? el('p', { class: 'aide' }, aide) : null, lignes,
      el('div', { class: 'cases' },
        el('button', { type: 'button', onclick: () => {
          // La plage suivante reprend les heures de la précédente, le jour d'après :
          // c'est le cas courant (mardi et jeudi, mêmes heures).
          const der = rangs[rangs.length - 1];
          const jour = der ? D.jours[(D.jours.indexOf(der.j.value) + 1) % 7] : 'lundi';
          ajouter(jour, der && der.d.value, der && der.f.value);
        } }, '+ Ajouter une plage')));
    return { bloc, valeur: () => rangs.map(r => ({ jour: r.j.value, debut: r.d.value, fin: r.f.value })) };
  }

  /** Le point de l'annonce : un clic sur la carte, ou une adresse trouvée.
   *  Un clic demande sa commune à la Base adresse nationale (géocodage
   *  inverse) : c'est son code INSEE qui décide quelles zones la couvrent. */
  function choixPosition(legende) {
    const pos = { lat: null, lon: null, commune: '', insee: '' };
    const marque = el('p', { class: 'aide' }, 'Aucun point placé. Cliquez sur la carte, ou cherchez une adresse.');
    let repere = null;
    const poser = (lat, lon) => {
      pos.lat = lat; pos.lon = lon;
      if (repere) carte.removeLayer(repere);
      repere = L.circleMarker([lat, lon], { radius: 9, color: '#111', weight: 3 }).addTo(carte);
      marque.textContent = `Point placé : ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    };
    async function communeDuPoint(lat, lon) {
      try {
        const r = await fetch(`${GEOCODAGE.replace('/search', '/reverse')}?lon=${lon}&lat=${lat}&limit=1`);
        const g = await r.json();
        const p = (g.features || [])[0];
        if (!p) return;
        pos.commune = p.properties.city || ''; pos.insee = p.properties.citycode || '';
        marque.textContent = `Point placé à ${pos.commune || 'une commune inconnue'} (${lat.toFixed(5)}, ${lon.toFixed(5)})`;
        if (pos.surChoix) pos.surChoix({ commune: pos.commune });
      } catch (_) { /* le serveur prendra la commune la plus proche */ }
    }
    const texte = el('input', { type: 'search', placeholder: 'Adresse ou commune' });
    const liste = el('div', { class: 'resultats-position' });
    const bouton = el('button', { type: 'button', onclick: async () => {
      liste.replaceChildren();
      try {
        const t = await geocoder(texte.value);
        t.forEach(r => liste.append(el('button', { type: 'button', onclick: () => {
          poser(r.lat, r.lon); pos.commune = r.commune || ''; pos.insee = r.insee || '';
          pos.adresse = r.type === 'municipality' ? '' : r.libelle;
          carte.setView([r.lat, r.lon], 13); liste.replaceChildren();
          if (pos.surChoix) pos.surChoix(r);
        } }, r.libelle)));
      } catch (err) { liste.append(el('span', { class: 'erreur' }, err.message)); }
    } }, 'Chercher');
    // Ce panneau-ci reçoit le prochain clic sur la carte.
    pos.activer = () => {
      etat.placement = (ll) => { poser(ll.lat, ll.lng); pos.insee = ''; pos.adresse = ''; communeDuPoint(ll.lat, ll.lng); };
    };
    pos.nettoyer = () => { if (repere) carte.removeLayer(repere); };
    pos.bloc = el('fieldset', {}, el('legend', {}, legende || 'Position sur la carte'),
      el('div', { class: 'cases' }, texte, bouton), liste, marque);
    return pos;
  }

  function ouvrirPublierEmplacement() {
    if (!permis('publier_emplacement') || etat.compte.verification === 'refuse') {
      ouvrir(el('h2', {}, 'Publier une recherche'),
        el('p', { class: 'info' }, etat.compte.verification === 'refuse'
          ? `La modération a refusé ce compte : il ne peut pas publier. Motif : ${etat.compte.verification_motif || 'non précisé'}.`
          : 'La publication est fermée pour le moment.'));
      return;
    }
    const message = el('p', { class: 'erreur', role: 'alert' });
    const genre = { valeur: 'besoin' };
    const titre = el('input', { type: 'text', required: true, maxlength: '120', placeholder: 'Un boulanger le mardi matin' });
    const commune = el('input', { type: 'text', required: true, maxlength: '120', value: etat.compte.commune || '' });
    const adresse = el('input', { type: 'text', maxlength: '200' });
    const elec = selectTriEtat();
    const eau = selectTriEtat();
    const redevance = el('input', { type: 'text', maxlength: '200', placeholder: 'Gratuit, 10 € par jour…' });
    const conditionsTxt = el('textarea', { rows: '2', maxlength: '2000' });
    const description = el('textarea', { rows: '3', maxlength: '3000' });
    const plages = editeurPlages('Créneaux souhaités',
      'Les jours et heures où vous aimeriez accueillir le service. Sans créneau, tous les services de la zone vous sont signalés.');
    const souhaitees = casesActivites('Services recherchés (aucun coché : tous)');
    const exclues = casesActivites('Services exclus');
    const pos = choixPosition('Où ?');
    pos.surChoix = (r) => { if (r.commune) commune.value = r.commune; if (pos.adresse) adresse.value = pos.adresse; };
    const choixGenre = el('fieldset', {}, el('legend', {}, 'Le lieu'),
      el('div', { class: 'cases' }, ...[['besoin', 'Sans lieu fixé : notre commune'], ['emplacement', 'Un emplacement précis']].map(([v, l]) =>
        el('label', { class: 'case' }, el('input', { type: 'radio', name: 'genre', value: v, checked: v === genre.valeur, onchange: () => { genre.valeur = v; } }), l))));

    const f = el('form', { class: 'formulaire', onsubmit: async (e) => {
      e.preventDefault();
      try {
        const r = await api('/api/emplacements', {
          genre: genre.valeur, titre: titre.value, commune: commune.value, code_insee: pos.insee,
          adresse: adresse.value, latitude: pos.lat, longitude: pos.lon, plages: plages.valeur(),
          electricite: valeurTriEtat(elec), eau: valeurTriEtat(eau),
          redevance: redevance.value, conditions: conditionsTxt.value, description: description.value,
          activites_souhaitees: souhaitees.valeur(), activites_exclues: exclues.valeur(),
        });
        pos.nettoyer();
        await rechargerCarte();
        await ouvrirFiche(r.id, r.services_trouves
          ? `Recherche publiée. ${r.services_trouves} service${r.services_trouves > 1 ? 's' : ''} déjà déclaré${r.services_trouves > 1 ? 's' : ''} dans votre secteur y correspond${r.services_trouves > 1 ? 'ent' : ''} : voir vos notifications.`
          : 'Recherche publiée. Vous serez prévenu quand un service de votre secteur y correspondra.');
        lireNotifications();
      } catch (err) { message.textContent = err.message; }
    } }, el('p', { class: 'aide' }, 'Dites quels commerces ou services ambulants vous recherchez. Les services dont la zone d’action couvre votre commune, et dont les horaires conviennent, vous seront signalés.'),
    champ('Titre', titre), souhaitees.bloc, plages.bloc, choixGenre, pos.bloc, champ('Commune', commune),
    champ('Adresse (emplacement précis)', adresse), champ('Électricité', elec), champ('Eau', eau),
    champ('Redevance d’occupation', redevance, 'Laisser vide si elle n’est pas encore fixée.'),
    exclues.bloc, champ('Conditions', conditionsTxt), champ('Description', description),
    avertissementLegal(), message, el('button', { type: 'submit', class: 'principal' }, 'Publier'));
    ouvrir(el('h2', {}, 'Publier une recherche de service'), f);
    pos.activer();
  }

  // ------------------------------------------------------------------
  // Les zones d'action d'un service : une ville, un cercle, un dessin
  // ------------------------------------------------------------------

  const STYLE_ZONE = { color: '#c2410c', weight: 2, fillOpacity: 0.12 };

  /** La couche Leaflet d'une zone (reçue du serveur ou en cours de saisie). */
  function coucheZone(z) {
    if (z.genre === 'polygone') return L.polygon(z.polygone || z.points, STYLE_ZONE);
    if (z.genre === 'cercle') return L.circle([z.lat, z.lon], { ...STYLE_ZONE, radius: z.rayon_km * 1000 });
    return L.circleMarker([z.lat, z.lon], { ...STYLE_ZONE, radius: 12, fillOpacity: 0.35 })
      .bindTooltip(z.libelle || '', { permanent: true, direction: 'top' });
  }

  /** Montre des zones sur la carte et les cadre. */
  function afficherZones(zones) {
    calqueZones.clearLayers();
    const couches = zones.map(z => coucheZone(z).addTo(calqueZones));
    if (!couches.length) return;
    const g = L.featureGroup(couches);
    carte.fitBounds(g.getBounds().pad(0.15), { maxZoom: 12 });
  }

  function editeurZones(pos) {
    const zones = []; // { envoi, libelle, nombre, couche }
    const liste = el('div');
    const outil = el('div');
    const rappel = el('p', { class: 'aide' }, 'Aucune zone pour l’instant.');

    function redessinerListe() {
      liste.replaceChildren(...zones.map((z, i) => el('div', { class: 'carte-liste' },
        el('strong', {}, z.libelle), ' — ', `${z.nombre} commune${z.nombre > 1 ? 's' : ''}`,
        el('details', {}, el('summary', {}, 'Voir les villes'),
          el('p', { class: 'aide' }, z.communes.map(c => c.nom).join(', ') + (z.nombre > z.communes.length ? '…' : ''))),
        el('div', { class: 'cases' },
          el('button', { type: 'button', onclick: () => carte.fitBounds(L.featureGroup([z.couche]).getBounds().pad(0.2), { maxZoom: 12 }) }, 'Voir la zone'),
          el('button', { type: 'button', class: 'danger', onclick: () => {
            calqueZones.removeLayer(z.couche); zones.splice(i, 1); redessinerListe();
          } }, 'Retirer')))));
      rappel.hidden = zones.length > 0;
    }

    async function ajouter(envoi) {
      const a = await api('/api/zones/apercu', { zone: envoi });
      const vue = envoi.genre === 'ville' ? { ...envoi, libelle: a.libelle } : envoi;
      const couche = coucheZone(vue).addTo(calqueZones);
      zones.push({ envoi, libelle: a.libelle, nombre: a.nombre, communes: a.communes, couche });
      redessinerListe();
      outil.replaceChildren();
      pos.activer();
    }

    function outilVille() {
      const texte = el('input', { type: 'search', placeholder: 'Nom de la commune' });
      const res = el('div', { class: 'resultats-position' });
      const msg = el('p', { class: 'erreur' });
      const chercher = async () => {
        res.replaceChildren();
        try {
          const r = await api(`/api/communes?q=${encodeURIComponent(texte.value)}`);
          if (!r.communes.length) res.append(el('span', { class: 'aide' }, 'Aucune commune trouvée.'));
          r.communes.forEach(c => res.append(el('button', { type: 'button', onclick: async () => {
            try { await ajouter({ genre: 'ville', code_insee: c.code_insee, lat: c.lat, lon: c.lon }); } catch (err) { msg.textContent = err.message; }
          } }, `${c.nom} (${c.departement})`)));
        } catch (err) { msg.textContent = err.message; }
      };
      texte.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); chercher(); } });
      outil.replaceChildren(el('div', { class: 'outil-zone' }, el('strong', {}, 'Une ville'),
        el('div', { class: 'cases' }, texte, el('button', { type: 'button', onclick: chercher }, 'Chercher')), res, msg));
      texte.focus();
    }

    function outilCercle() {
      const centre = { lat: pos.lat, lon: pos.lon };
      const rayon = el('input', { type: 'number', min: '1', max: '300', step: '1', value: '20' });
      const nb = el('p', { class: 'aide' });
      const msg = el('p', { class: 'erreur' });
      let apercu = null;
      let minuteur = null;
      const redessiner = () => {
        if (apercu) carte.removeLayer(apercu);
        const r = parseFloat(rayon.value);
        if (centre.lat === null || !(r > 0)) { nb.textContent = 'Cliquez sur la carte pour placer le centre.'; return; }
        apercu = L.circle([centre.lat, centre.lon], { ...STYLE_ZONE, dashArray: '6 4', radius: r * 1000 }).addTo(carte);
        // L'aperçu demande au serveur combien de communes le cercle couvre,
        // sans le harceler à chaque chiffre tapé.
        clearTimeout(minuteur);
        minuteur = setTimeout(async () => {
          try {
            const a = await api('/api/zones/apercu', { zone: { genre: 'cercle', lat: centre.lat, lon: centre.lon, rayon_km: r } });
            nb.textContent = `${a.nombre} commune${a.nombre > 1 ? 's' : ''} dans ce cercle.`;
          } catch (err) { nb.textContent = err.message; }
        }, 300);
      };
      rayon.addEventListener('input', redessiner);
      etat.placement = (ll) => { centre.lat = ll.lat; centre.lon = ll.lng; redessiner(); };
      const fin = () => { if (apercu) carte.removeLayer(apercu); outil.replaceChildren(); pos.activer(); };
      outil.replaceChildren(el('div', { class: 'outil-zone' }, el('strong', {}, 'Un cercle'),
        el('p', { class: 'aide' }, 'Le centre est votre position ; cliquez sur la carte pour le déplacer.'),
        champ('Rayon (km)', rayon), nb, msg,
        el('div', { class: 'cases' },
          el('button', { type: 'button', class: 'principal', onclick: async () => {
            try {
              const envoi = { genre: 'cercle', lat: centre.lat, lon: centre.lon, rayon_km: parseFloat(rayon.value) };
              if (apercu) carte.removeLayer(apercu);
              await ajouter(envoi);
            } catch (err) { msg.textContent = err.message; }
          } }, 'Ajouter ce cercle'),
          el('button', { type: 'button', onclick: fin }, 'Annuler'))));
      redessiner();
    }

    /** À main levée : on appuie sur la carte et on trace sans lever le
     *  doigt (ou la souris). Pendant le tracé, la carte ne bouge plus. */
    function outilDessin() {
      const msg = el('p', { class: 'erreur' });
      const aide = el('p', { class: 'aide' }, 'Appuyez sur la carte et tracez le contour de votre zone sans lever le doigt. La carte est figée pendant le tracé.');
      const conteneur = carte.getContainer();
      let points = [];
      let trace = null;
      let enCours = false;
      etat.placement = null;
      carte.dragging.disable();
      conteneur.classList.add('en-trace');
      const latlng = (e) => carte.containerPointToLatLng(L.point(e.clientX - conteneur.getBoundingClientRect().left, e.clientY - conteneur.getBoundingClientRect().top));
      const dernierPx = { x: 0, y: 0 };
      const bas = (e) => {
        if (e.button !== undefined && e.button !== 0) return;
        enCours = true; points = [];
        if (trace) carte.removeLayer(trace);
        trace = L.polyline([], { ...STYLE_ZONE, dashArray: '4 4' }).addTo(carte);
        conteneur.setPointerCapture && conteneur.setPointerCapture(e.pointerId);
        bouge(e, true);
        e.preventDefault();
      };
      const bouge = (e, force) => {
        if (!enCours) return;
        // Un point tous les 6 pixels : assez pour suivre la main, pas au
        // point de dépasser les 500 points qu'accepte le serveur.
        if (!force && Math.hypot(e.clientX - dernierPx.x, e.clientY - dernierPx.y) < 6) return;
        dernierPx.x = e.clientX; dernierPx.y = e.clientY;
        const p = latlng(e);
        points.push([p.lat, p.lng]);
        trace.addLatLng(p);
      };
      const haut = async () => {
        if (!enCours) return;
        enCours = false;
        terminer();
        if (points.length < 3) { msg.textContent = 'Tracé trop court : recommencez.'; return; }
        // Trop de points : on en garde un sur n, le contour reste fidèle.
        const pas = Math.ceil(points.length / 480);
        const garde = points.filter((_, i) => i % pas === 0).map(([a, b]) => [+a.toFixed(5), +b.toFixed(5)]);
        if (trace) carte.removeLayer(trace);
        try { await ajouter({ genre: 'polygone', points: garde }); } catch (err) { msg.textContent = err.message; outilDessin(); }
      };
      const terminer = () => {
        conteneur.removeEventListener('pointerdown', bas);
        conteneur.removeEventListener('pointermove', bouge);
        conteneur.removeEventListener('pointerup', haut);
        carte.dragging.enable();
        conteneur.classList.remove('en-trace');
        document.body.classList.remove('trace-actif');
      };
      conteneur.addEventListener('pointerdown', bas);
      conteneur.addEventListener('pointermove', bouge);
      conteneur.addEventListener('pointerup', haut);
      outil.replaceChildren(el('div', { class: 'outil-zone' }, el('strong', {}, 'Dessin à main levée'), aide, msg,
        el('button', { type: 'button', onclick: () => { terminer(); if (trace) carte.removeLayer(trace); outil.replaceChildren(); pos.activer(); } }, 'Annuler')));
      // Sur téléphone, le panneau couvre le bas de la carte : on le replie
      // le temps du tracé.
      document.body.classList.add('trace-actif');
    }

    const bloc = el('fieldset', {}, el('legend', {}, 'Mes zones d’action'),
      el('p', { class: 'aide' }, 'Où allez-vous ? Une ou plusieurs zones : une ville, un cercle autour d’un point, ou un contour dessiné sur la carte. Les mairies de ces zones qui recherchent votre activité seront prévenues. Une commune compte si son centre est dans la zone.'),
      rappel, liste, outil,
      el('div', { class: 'cases' },
        el('button', { type: 'button', onclick: outilVille }, '+ Une ville'),
        el('button', { type: 'button', onclick: outilCercle }, '+ Un cercle'),
        el('button', { type: 'button', onclick: outilDessin }, '+ Dessiner une zone')));
    return { bloc, valeur: () => zones.map(z => z.envoi) };
  }

  function ouvrirPublierDemande() {
    const message = el('p', { class: 'erreur', role: 'alert' });
    const titre = el('input', { type: 'text', required: true, maxlength: '120', placeholder: 'Pizzas au feu de bois' });
    const categorie = el('select', { required: true }, ...CATEGORIES.map(c => el('option', { value: c.cle }, c.libelle)));
    const activite = el('select', { required: true });
    const champsBloc = el('div');
    const avert = el('div');
    let champs = [];
    function selonCategorie() {
      const c = CAT[categorie.value];
      activite.replaceChildren(...c.activites.map(a => el('option', { value: a.cle }, a.libelle)));
      champs = c.champs.map(ch => ({ ch, controle: ch.genre === 'oui_non' ? selectTriEtat() : el('input', { type: 'text', maxlength: '200' }) }));
      champsBloc.replaceChildren(...champs.map(x => champ(x.ch.libelle, x.controle)));
      avert.replaceChildren(c.avertissement ? avertissementLegal(c.avertissement) : '');
    }
    categorie.addEventListener('change', selonCategorie);
    (etat.compte.categories || []).slice(0, 1).forEach(c => { categorie.value = c; });
    selonCategorie();
    const commune = el('input', { type: 'text', maxlength: '120' });
    const elec = selectTriEtat();
    const eau = selectTriEtat();
    const surface = el('input', { type: 'number', min: '1', max: '500', step: '0.5' });
    const description = el('textarea', { rows: '3', maxlength: '3000' });
    const plages = editeurPlages('Mes disponibilités',
      'Les jours et heures où vous pouvez venir. Une mairie n’est prévenue que si ses créneaux recoupent les vôtres.');
    const pos = choixPosition('Où êtes-vous installé ?');
    pos.surChoix = (r) => { if (r.commune) commune.value = r.commune; };
    const zones = editeurZones(pos);

    const f = el('form', { class: 'formulaire', onsubmit: async (e) => {
      e.preventDefault();
      const champsActivite = {};
      champs.forEach(({ ch, controle }) => {
        const v = ch.genre === 'oui_non' ? valeurTriEtat(controle) : controle.value.trim();
        if (v !== null && v !== '') champsActivite[ch.cle] = v;
      });
      try {
        const r = await api('/api/demandes', {
          titre: titre.value, categorie: categorie.value, activite: activite.value,
          latitude: pos.lat, longitude: pos.lon, commune: commune.value,
          zones: zones.valeur(), plages: plages.valeur(),
          besoin_electricite: valeurTriEtat(elec), besoin_eau: valeurTriEtat(eau),
          surface_m2: surface.value || null, champs_activite: champsActivite, description: description.value,
        });
        pos.nettoyer();
        await rechargerCarte();
        const n = r.mairies_prevenues;
        await ouvrirMonCompte(n
          ? `Demande publiée : ${n} mairie${n > 1 ? 's' : ''} prévenue${n > 1 ? 's' : ''}.`
          : 'Demande publiée. Aucune mairie de vos zones ne recherche votre activité pour l’instant : elles seront prévenues dès qu’elles le feront.');
      } catch (err) { message.textContent = err.message; }
    } }, champ('Titre', titre), champ('Catégorie', categorie), champ('Activité', activite), champsBloc, avert,
    pos.bloc, champ('Commune', commune), zones.bloc, plages.bloc,
    champ('Besoin d’électricité', elec), champ('Besoin d’eau', eau), champ('Surface nécessaire (m²)', surface),
    champ('Description', description), avertissementLegal(), message, el('button', { type: 'submit', class: 'principal' }, 'Publier'));
    ouvrir(el('h2', {}, 'Proposer mes services'), f);
    pos.activer();
  }

  // ------------------------------------------------------------------
  // La console : vérification des accueillants, droits, comptes
  // ------------------------------------------------------------------

  document.getElementById('bouton-console').addEventListener('click', () => ouvrirConsole());

  async function ouvrirConsole() {
    const blocs = [el('h2', {}, 'Console')];
    if (permis('mod_verifier_accueillants')) {
      blocs.push(el('h3', {}, 'Accueillants à vérifier (badge)'));
      try {
        const r = await api('/api/moderation/accueillants');
        if (!r.comptes.length) blocs.push(el('p', { class: 'aide' }, 'Aucun compte en attente.'));
        r.comptes.forEach(c => {
          const motif = el('input', { type: 'text', placeholder: 'Motif du refus' });
          const msg = el('p', { class: 'aide' });
          const decider = async (decision) => {
            try { await api(`/api/moderation/accueillants/${c.identifiant}`, { decision, motif: motif.value }); ouvrirConsole(); } catch (err) { msg.textContent = err.message; msg.className = 'erreur'; }
          };
          blocs.push(el('div', { class: 'carte-liste' },
            el('strong', {}, c.organisation || c.pseudo), ` (${c.nature_libelle || '?'}, ${c.commune || 'commune non renseignée'})`,
            el('div', { class: 'aide' }, `${c.pseudo} · ${c.email} · inscrit le ${c.date_creation.slice(0, 10)}`),
            el('div', { class: 'cases' }, el('button', { type: 'button', class: 'principal', onclick: () => decider('verifie') }, 'Vérifié'),
              motif, el('button', { type: 'button', class: 'danger', onclick: () => decider('refuse') }, 'Refuser')), msg));
        });
      } catch (err) { blocs.push(el('p', { class: 'erreur' }, err.message)); }
    }
    if (permis('adm_droits')) {
      blocs.push(el('h3', {}, 'Tableau des droits'));
      try { blocs.push(tableauDroits(await api('/api/admin/droits'))); } catch (err) { blocs.push(el('p', { class: 'erreur' }, err.message)); }
    }
    if (permis('adm_comptes')) {
      blocs.push(el('h3', {}, 'Comptes et rôles'));
      try {
        const r = await api('/api/admin/comptes');
        const t = el('table', { class: 'tableau' }, el('tr', {}, el('th', {}, 'Compte'), el('th', {}, 'Type'), el('th', {}, 'Rôle')));
        r.comptes.forEach(c => {
          const s = el('select', {}, ...['utilisateur', 'moderateur', 'administrateur'].map(x => el('option', { value: x, selected: x === c.role }, x)));
          s.addEventListener('change', async () => {
            try { await api(`/api/admin/comptes/${c.identifiant}/role`, { role: s.value }); } catch (err) { alert(err.message); s.value = c.role; }
          });
          t.append(el('tr', {}, el('td', {}, c.pseudo, el('div', { class: 'aide' }, c.email)), el('td', {}, c.type_compte), el('td', {}, s)));
        });
        blocs.push(t);
      } catch (err) { blocs.push(el('p', { class: 'erreur' }, err.message)); }
    }
    ouvrir(...blocs);
  }

  function tableauDroits(t) {
    const table = el('table', { class: 'tableau' }, el('tr', {}, el('th', {}, 'Fonction'), el('th', {}, 'Niveau'), el('th', {}, 'Active')));
    let famille = '';
    t.fonctionnalites.forEach(f => {
      if (f.famille !== famille) { famille = f.famille; table.append(el('tr', {}, el('th', { colspan: '3' }, famille))); }
      const plancher = t.niveaux.findIndex(n => n.valeur === f.plancher);
      const niveau = el('select', { disabled: f.verrouillee },
        ...t.niveaux.map((n, i) => el('option', { value: n.valeur, selected: n.valeur === f.niveau, disabled: i < plancher }, n.libelle)));
      niveau.addEventListener('change', async () => {
        try { await api('/api/admin/droits', { cle: f.cle, niveau: niveau.value }); await lireSession(); } catch (err) { alert(err.message); niveau.value = f.niveau; }
      });
      const active = el('input', { type: 'checkbox', checked: f.active, disabled: !f.desactivable });
      active.addEventListener('change', async () => {
        try { await api('/api/admin/droits', { cle: f.cle, active: active.checked }); await lireSession(); } catch (err) { alert(err.message); active.checked = f.active; }
      });
      const precisions = [f.pour ? { accueillant: 'comptes accueillants', commercant: 'comptes commerçants' }[f.pour] : '', f.controle === 'ecran' ? 'tenue par l’écran seulement' : '', f.verrouillee ? 'verrouillée' : ''].filter(Boolean).join(' · ');
      table.append(el('tr', {}, el('td', {}, f.libelle, precisions ? el('div', { class: 'aide' }, precisions) : null), el('td', {}, niveau), el('td', {}, active)));
    });
    return table;
  }

  // ------------------------------------------------------------------
  // Démarrage
  // ------------------------------------------------------------------

  dessiner();
  lireSession();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* la carte marche sans */ });
  }
})();
