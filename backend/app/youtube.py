"""Téléchargement de l'audio d'une vidéo YouTube publique ou non répertoriée (yt-dlp, bibliothèque).

Sécurité :
 - seules les URL https://youtube.com | www.youtube.com | m.youtube.com | youtu.be sont acceptées ;
   l'identifiant de vidéo (11 caractères) est extrait et l'URL est RECONSTRUITE : rien d'autre n'est transmis à yt-dlp ;
 - pas de playlist, pas de cookies, pas de fichier de configuration, pas de post-traitement (aucun programme externe lancé) ;
 - audio seul, durée et taille plafonnées.
"""
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_DURATION = 8 * 3600          # 8 h
MAX_BYTES = 2 * 1024 ** 3        # 2 Go d'audio
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_PATH_ID = re.compile(r"^/(?:shorts|live|embed|v)/([A-Za-z0-9_-]{11})(?:/|$)")


class YoutubeError(Exception):
    """Erreur affichable à l'utilisateur."""


def video_id(url: str) -> str:
    """Extrait l'identifiant d'une URL YouTube ; lève YoutubeError si l'URL n'est pas acceptable."""
    try:
        u = urlparse((url or "").strip())
    except ValueError as e:
        raise YoutubeError("Lien invalide.") from e
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443):
        raise YoutubeError("Le lien doit commencer par https:// et pointer vers YouTube.")
    host = (u.hostname or "").lower()
    vid = None
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host in _HOSTS:
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        elif m := _PATH_ID.match(u.path):
            vid = m.group(1)
    else:
        raise YoutubeError("Seuls les liens YouTube (youtube.com, youtu.be) sont acceptés.")
    if not vid or not _ID.match(vid):
        raise YoutubeError("Lien de vidéo YouTube non reconnu (les playlists et chaînes ne sont pas encore prises en charge).")
    return vid


def canonical_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


_HINTS = (
    ("private video", "Cette vidéo est privée : seules les vidéos publiques et non répertoriées sont prises en charge pour l'instant."),
    ("sign in", "YouTube demande une connexion pour cette vidéo (privée, réservée aux membres ou avec limite d'âge). Non pris en charge pour l'instant."),
    ("members-only", "Vidéo réservée aux membres : non prise en charge pour l'instant."),
    ("video unavailable", "Vidéo indisponible (supprimée ou bloquée dans ton pays)."),
    ("not available", "Vidéo indisponible (supprimée ou bloquée dans ton pays)."),
    ("live event", "Le direct n'est pas terminé : réessaie une fois la diffusion finie."),
    ("is live", "Le direct n'est pas terminé : réessaie une fois la diffusion finie."),
    ("urlopen error", "Impossible de joindre YouTube : vérifie ta connexion internet."),
    ("getaddrinfo", "Impossible de joindre YouTube : vérifie ta connexion internet."),
    ("http error 429", "YouTube limite temporairement les requêtes : réessaie dans quelques minutes."),
)


def friendly(err: Exception) -> str:
    msg = str(err)
    low = msg.lower()
    for key, text in _HINTS:
        if key in low:
            return text
    return "Téléchargement impossible : " + re.sub(r"\x1b\[[0-9;]*m|ERROR:\s*", "", msg).strip()[:300]


def download_audio(url: str, dest_dir: Path, on_progress: Callable[[float, str], None] | None = None) -> tuple[Path, dict]:
    """Télécharge l'audio dans dest_dir. Retourne (fichier, métadonnées {title, duration, id})."""
    import yt_dlp

    vid = video_id(url)
    def hook(d: dict) -> None:
        if d.get("status") == "downloading" and on_progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total > MAX_BYTES:
                raise YoutubeError("Fichier audio trop volumineux.")
            if total:
                on_progress(d.get("downloaded_bytes", 0) / total, "Téléchargement de l'audio YouTube…")

    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "noplaylist": True,
        "source_address": "0.0.0.0",      # noqa: S104 - IPv4 : les URL signées sont liées à l'IP, l'IPv6 échoue souvent
        "socket_timeout": 30,
        "retries": 3,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "fixup": "never",                 # pas de ffmpeg requis ; PyAV lit le fichier tel quel
        "postprocessors": [],
        "cachedir": False,
        "ignoreconfig": True,
        "match_filter": lambda info, incomplete=False: (
            f"Vidéo trop longue (plus de {MAX_DURATION // 3600} h)." if (info.get("duration") or 0) > MAX_DURATION else None),
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(canonical_url(vid), download=True)
    except YoutubeError:
        raise
    except Exception as e:  # noqa: BLE001 - yt-dlp lève des types variés
        raise YoutubeError(friendly(e)) from e
    files = sorted(dest_dir.glob("source.*"))
    if not info or not files:
        raise YoutubeError("Aucun fichier audio n'a été téléchargé (vidéo trop longue ou indisponible ?).")
    return files[0], {"title": (info.get("title") or "Vidéo YouTube")[:120], "duration": info.get("duration"), "id": vid}
