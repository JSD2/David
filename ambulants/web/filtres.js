// Les filtres de la carte (22 octobre) : activité précise, jour et heure,
// équipements du lieu, confiance, fraîcheur.
//
// Module à part, sans dépendance à la page : la même fonction trie la carte
// et se fait éprouver sous Node (tests/js/filtres.test.mjs).
//
// **Ce qu'on ne sait pas n'est pas « non ».** Une annonce sans horaires
// n'est écartée par un jour choisi que si l'on a décoché « inclure les
// annonces sans horaires » ; un équipement non renseigné ne passe que si
// l'on a choisi « oui ou non renseigné ».
'use strict';

(function (racine) {
  const JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'];

  /** Les filtres par défaut : rien d'écarté. */
  function vides() {
    return {
      categorie: '', activite: '',
      jour: '', debut: '', fin: '', sansHoraires: true,
      electricite: '', eau: '', gratuit: '', // '' | 'oui' | 'oui_inconnu'
      mairiesVerifiees: false,
      ageJours: 0, // 0 : toutes dates
    };
  }

  function minutes(h) {
    const m = /^(\d{2}):(\d{2})$/.exec(h || '');
    return m ? (+m[1]) * 60 + (+m[2]) : null;
  }

  /** L'annonce est-elle là ce jour-là, sur cette plage d'heures ? */
  function disponible(a, f) {
    const plages = a.plages || [];
    if (!plages.length) {
      // Les annonces d'avant les plages horaires n'ont que des jours.
      if ((a.jours || []).length) return a.jours.includes(f.jour);
      return f.sansHoraires;
    }
    const d = minutes(f.debut);
    const fin = minutes(f.fin);
    return plages.some(p => p.jour === f.jour
      && (d === null || minutes(p.fin) > d)
      && (fin === null || minutes(p.debut) < fin));
  }

  function equipement(valeur, choix) {
    if (!choix) return true;
    if (valeur === true) return true;
    return choix === 'oui_inconnu' && (valeur === null || valeur === undefined);
  }

  /** `activites` : la catégorie et l'activité de chaque clé connue. */
  function correspond(a, f, activites, maintenant) {
    // Activité : un service propose une activité ; un emplacement en
    // accepte, et une recherche sans activité cochée les accepte toutes.
    if (f.categorie || f.activite) {
      if (a.sens === 'demande') {
        if (f.activite ? a.activite !== f.activite : a.categorie !== f.categorie) return false;
      } else {
        const exclues = a.exclues || [];
        if (f.activite && (exclues.includes(f.activite) || exclues.includes(f.categorie))) return false;
        if (!f.activite && exclues.includes(f.categorie)) return false;
        const acc = a.activites || [];
        if (acc.length) {
          const ok = acc.some(x => {
            const cat = activites[x] ? activites[x].categorie : x;
            if (f.activite) return x === f.activite || x === f.categorie;
            return x === f.categorie || cat === f.categorie;
          });
          if (!ok) return false;
        }
      }
    }
    if (f.jour && !disponible(a, f)) return false;
    // Équipements : ceux du lieu proposé par une mairie. Un service n'en
    // propose pas : ces filtres ne le concernent pas.
    if (a.sens === 'emplacement'
        && !(equipement(a.electricite, f.electricite) && equipement(a.eau, f.eau) && equipement(a.gratuit, f.gratuit))) return false;
    if (f.mairiesVerifiees && a.sens === 'emplacement' && !a.verifie) return false;
    if (f.ageJours > 0) {
      const t = Date.parse(a.date || '');
      if (Number.isNaN(t) || (maintenant - t) > f.ageJours * 86400000) return false;
    }
    return true;
  }

  /** Les filtres actifs, en mots, pour les pastilles. */
  function actifs(f, libelles) {
    const v = vides();
    const sortie = [];
    if (f.activite) sortie.push({ cles: ['activite'], texte: libelles(f.activite) });
    else if (f.categorie) sortie.push({ cles: ['categorie'], texte: libelles(f.categorie) });
    if (f.jour) {
      const heures = f.debut || f.fin ? ` ${f.debut || '…'}–${f.fin || '…'}` : '';
      sortie.push({ cles: ['jour', 'debut', 'fin', 'sansHoraires'], texte: `${f.jour}${heures}` });
    }
    const eq = { electricite: 'Électricité', eau: 'Eau', gratuit: 'Gratuit' };
    for (const k of Object.keys(eq)) {
      if (f[k]) sortie.push({ cles: [k], texte: eq[k] + (f[k] === 'oui_inconnu' ? ' (ou non renseigné)' : '') });
    }
    if (f.mairiesVerifiees) sortie.push({ cles: ['mairiesVerifiees'], texte: 'Mairies vérifiées' });
    if (f.ageJours) sortie.push({ cles: ['ageJours'], texte: `Moins de ${f.ageJours} jours` });
    return sortie.map(x => ({ ...x, remise: Object.fromEntries(x.cles.map(k => [k, v[k]])) }));
  }

  const Filtres = { JOURS, vides, correspond, actifs };
  if (typeof module !== 'undefined' && module.exports) module.exports = Filtres;
  else racine.Filtres = Filtres;
})(typeof window !== 'undefined' ? window : globalThis);
