"""Géométrie des zones d'action : cercle, dessin à main levée, ville.

Calculs plans sur la latitude et la longitude, sauf les distances, en
grand cercle. À l'échelle d'une zone de tournée (quelques dizaines de
kilomètres), l'écart avec un calcul exact est sans effet sur la question
posée : le centre de telle commune est-il dedans ?
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

RAYON_TERRE_KM = 6371.0
#: Une zone ne dépasse pas cette étendue : au-delà, ce n'est plus une
#: tournée, et la liste des communes deviendrait illisible.
RAYON_MAX_KM = 300.0
ETENDUE_MAX_KM = 600.0
POINTS_MAX = 500


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAYON_TERRE_KM * math.asin(min(1.0, math.sqrt(a)))


def boite_cercle(lat: float, lon: float, rayon_km: float) -> Tuple[float, float, float, float]:
    """(lat min, lat max, lon min, lon max) qui contient le cercle."""
    dlat = rayon_km / 111.2
    dlon = rayon_km / (111.2 * max(0.01, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def boite_polygone(points: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return min(lats), max(lats), min(lons), max(lons)


def dans_polygone(lat: float, lon: float, points: Sequence[Sequence[float]]) -> bool:
    """Lancer de rayon : le point est dedans si une demi-droite issue de lui
    coupe le contour un nombre impair de fois."""
    dedans = False
    n = len(points)
    j = n - 1
    for i in range(n):
        yi, xi = points[i]
        yj, xj = points[j]
        if (yi > lat) != (yj > lat):
            x = xi + (lat - yi) * (xj - xi) / (yj - yi)
            if lon < x:
                dedans = not dedans
        j = i
    return dedans


def valider_polygone(brut) -> List[List[float]]:
    """Une liste de [lat, lon] lisible, ou ValueError avec la raison."""
    if not isinstance(brut, list) or len(brut) < 3:
        raise ValueError("Un dessin demande au moins trois points.")
    if len(brut) > POINTS_MAX:
        raise ValueError(f"Un dessin compte au plus {POINTS_MAX} points.")
    points = []
    for p in brut:
        try:
            lat, lon = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise ValueError("Un point du dessin est illisible.")
        if not (math.isfinite(lat) and math.isfinite(lon)
                and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Un point du dessin est hors de la carte.")
        points.append([round(lat, 6), round(lon, 6)])
    la0, la1, lo0, lo1 = boite_polygone(points)
    if (distance_km(la0, lo0, la1, lo0) > ETENDUE_MAX_KM
            or distance_km(la0, lo0, la0, lo1) > ETENDUE_MAX_KM):
        raise ValueError(f"Le dessin dépasse {ETENDUE_MAX_KM:g} km de côté.")
    return points
