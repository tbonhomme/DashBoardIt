"""Icône de l'application (générée par code : aucun fichier image à fournir)."""
from __future__ import annotations

from PIL import Image, ImageDraw


def creer_icone(chrono_actif: bool = False, taille: int = 64) -> Image.Image:
    s = taille * 4                                   # dessin en grand puis réduction (bords lissés)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([s * 0.04, s * 0.04, s * 0.96, s * 0.96], radius=s * 0.2, fill=(31, 78, 121, 255))
    d.line([(s * 0.25, s * 0.52), (s * 0.43, s * 0.70), (s * 0.76, s * 0.30)], fill=(255, 255, 255, 255),
           width=int(s * 0.11), joint="curve")
    if chrono_actif:                                  # pastille rouge = un chrono tourne
        r, cx, cy = s * 0.2, s * 0.77, s * 0.77
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(220, 38, 38, 255), outline=(255, 255, 255, 255), width=int(s * 0.04))
    return img.resize((taille, taille), Image.LANCZOS)


def enregistrer_ico(chemin: str) -> None:
    creer_icone(False, 256).save(chemin, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
