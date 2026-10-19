"""Les catégories de services ambulants, et ce qui est propre à chacune.

Des catégories claires dès le départ, pour que la carte se filtre et qu'un
accueillant dise « pas de restauration » sans texte libre. La liste vient
du document de passation (alimentaire, services, santé, administratif…) ;
elle s'allonge ici, et nulle part ailleurs.

**Les avertissements** ne disent pas le droit : ils rappellent qu'une
activité est réglementée et que le site ne vérifie rien. Ils s'affichent là
où l'on décide (fiche, publication).

**Les champs propres** à une catégorie sont des questions oui / non ou des
textes courts. Une question sans réponse reste sans réponse : elle n'est
jamais enregistrée comme « non ».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class Champ:
    cle: str
    libelle: str
    genre: str = "oui_non"  # « oui_non » ou « texte »


@dataclass(frozen=True)
class Categorie:
    cle: str
    libelle: str
    couleur: str
    activites: Tuple[Tuple[str, str], ...]
    avertissement: str = ""
    champs: Tuple[Champ, ...] = field(default_factory=tuple)


_A_ALIMENTAIRE = (
    "Activité alimentaire : déclaration auprès des services vétérinaires "
    "(DDPP), règles d'hygiène et de chaîne du froid. Le site ne vérifie pas "
    "ces obligations.")
_A_SANTE = (
    "Activité de santé : profession réglementée (diplôme, inscription à "
    "l'ordre, conditions d'exercice en lieu mobile). Le site ne vérifie pas "
    "ces obligations.")

CATEGORIES: Tuple[Categorie, ...] = (
    Categorie(
        "alimentaire", "Alimentaire", "#c2410c",
        (("food_truck", "Food truck, restauration"),
         ("boulangerie", "Boulangerie, pâtisserie"),
         ("epicerie", "Épicerie, supérette"),
         ("primeur", "Fruits et légumes, producteur"),
         ("boucherie", "Boucherie, charcuterie, poissonnerie"),
         ("autre_alimentaire", "Autre commerce alimentaire")),
        avertissement=_A_ALIMENTAIRE,
        champs=(Champ("chaine_froid", "Vente de produits frais (chaîne du froid)"),
                Champ("cuisson_sur_place", "Cuisson sur place"),
                Champ("declaration_ddpp", "Déclaration DDPP faite"))),
    Categorie(
        "commerce", "Commerce non alimentaire", "#7c3aed",
        (("habillement", "Habillement, mercerie"),
         ("bazar", "Bazar, quincaillerie"),
         ("librairie", "Librairie, presse"),
         ("autre_commerce", "Autre commerce"))),
    Categorie(
        "services", "Services à la personne", "#0f766e",
        (("coiffure", "Coiffure, esthétique"),
         ("pressing", "Pressing, retouches"),
         ("numerique", "Aide numérique, informatique"),
         ("autre_service", "Autre service"))),
    Categorie(
        "sante", "Santé", "#be123c",
        (("medecin", "Cabinet médical mobile"),
         ("infirmier", "Soins infirmiers"),
         ("optique", "Optique, audition"),
         ("depistage", "Dépistage, prévention"),
         ("autre_sante", "Autre activité de santé")),
        avertissement=_A_SANTE,
        champs=(Champ("profession", "Profession exercée", "texte"),)),
    Categorie(
        "administratif", "Administratif", "#1d4ed8",
        (("france_services", "France services, bureau mobile"),
         ("poste", "Point postal"),
         ("banque", "Banque, distributeur"),
         ("autre_administratif", "Autre service administratif"))),
    Categorie(
        "artisanat", "Artisanat et dépannage", "#a16207",
        (("garage", "Garage, mécanique"),
         ("cordonnerie", "Cordonnerie, clés"),
         ("reparation", "Réparation (vélo, électroménager…)"),
         ("autre_artisan", "Autre artisan"))),
    Categorie(
        "culture", "Culture et loisirs", "#15803d",
        (("bibliotheque", "Médiathèque, bibliobus"),
         ("spectacle", "Spectacle, cinéma itinérant"),
         ("autre_culture", "Autre activité culturelle"))),
)

PAR_CLE: Dict[str, Categorie] = {c.cle: c for c in CATEGORIES}
#: Activité → catégorie, pour valider une paire reçue.
CATEGORIE_DE: Dict[str, str] = {a: c.cle for c in CATEGORIES for a, _ in c.activites}


def valider_paire(categorie: str, activite: str) -> bool:
    return CATEGORIE_DE.get(activite) == categorie


def valider_champs(categorie: str, recus: dict) -> dict:
    """Ne garde que les champs propres à la catégorie, bien formés.

    Une réponse absente ou illisible est écartée, pas convertie : un
    `None` reçu pour « chaîne du froid » ne devient pas « non ».
    """
    cat = PAR_CLE.get(categorie)
    if cat is None or not isinstance(recus, dict):
        return {}
    gardes = {}
    for champ in cat.champs:
        v = recus.get(champ.cle)
        if champ.genre == "oui_non" and isinstance(v, bool):
            gardes[champ.cle] = v
        elif champ.genre == "texte" and isinstance(v, str) and v.strip():
            gardes[champ.cle] = v.strip()[:200]
    return gardes


def pour_le_navigateur() -> list:
    return [
        {"cle": c.cle, "libelle": c.libelle, "couleur": c.couleur,
         "activites": [{"cle": a, "libelle": l} for a, l in c.activites],
         "avertissement": c.avertissement,
         "champs": [{"cle": ch.cle, "libelle": ch.libelle, "genre": ch.genre}
                    for ch in c.champs]}
        for c in CATEGORIES
    ]
