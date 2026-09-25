#!/usr/bin/env python3
"""ytbmp3: URL or local file to MP3, behind a small Flask UI."""

import os
import subprocess
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "mp3"
YT_DLP = os.environ.get("YT_DLP", str(Path.home() / ".local/bin/yt-dlp"))
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
TIMEOUT = 600

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# in memory only: a restart forgets running jobs
tasks: dict[str, dict] = {}


def fail(task_id, msg):
    tasks[task_id].update(status="error", error=msg)


def last_line(text):
    return text.strip().split("\n")[-1]


def convert_url(task_id: str, url: str):
    tasks[task_id]["status"] = "processing"
    cmd = [
        YT_DLP,
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--embed-thumbnail",
        "--add-metadata",
        "--no-playlist",
        "--concurrent-fragments", "4",
        "--print", "after_move:filepath",
        "-o", str(OUTPUT_DIR / "%(title)s.%(ext)s"),
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return fail(task_id, "Timeout : conversion trop longue (>10 min)")
    except FileNotFoundError:
        return fail(task_id, f"yt-dlp introuvable ({YT_DLP}). Installe-le avec : pip install yt-dlp")

    if proc.returncode != 0:
        return fail(task_id, last_line(proc.stderr))
    tasks[task_id].update(status="done", filename=Path(last_line(proc.stdout)).name)


def convert_file(task_id: str, src: Path):
    tasks[task_id]["status"] = "processing"
    name = src.stem + ".mp3"
    n = 1
    while (OUTPUT_DIR / name).exists():
        name = f"{src.stem}_{n}.mp3"
        n += 1

    cmd = [FFMPEG, "-i", str(src), "-vn", "-q:a", "0", "-map_metadata", "0", "-y", str(OUTPUT_DIR / name)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return fail(task_id, "Timeout : conversion trop longue (>10 min)")
    except FileNotFoundError:
        return fail(task_id, "ffmpeg introuvable. Installe-le avec : sudo apt install ffmpeg")
    finally:
        src.unlink(missing_ok=True)

    if proc.returncode != 0:
        return fail(task_id, last_line(proc.stderr))
    tasks[task_id].update(status="done", filename=name)


# one SEO landing page per platform, served at /<slug>
PLATFORMS = {
    "youtube-mp3": {
        "platform_name": "YouTube",
        "title": "Convertir YouTube en MP3 Gratuit — ytbmp3 | Sans Pub, Qualité Max",
        "h1": "Convertir YouTube en MP3",
        "description": "Convertis n'importe quelle vidéo YouTube en MP3 gratuitement. Sans pub, sans inscription, qualité 320 kbps. Colle le lien, télécharge le MP3.",
        "keywords": "youtube mp3, youtube to mp3, convertir youtube mp3, ytb mp3, youtube mp3 converter, telecharger youtube mp3, youtube en mp3 gratuit, youtube mp3 sans pub, download youtube mp3 free",
        "lead": "Convertis n'importe quelle vidéo YouTube en fichier MP3 haute qualité. Colle le lien, clique, télécharge. Pas de pub, pas d'inscription, pas de limite.",
        "points": [
            "Qualité maximale : 320 kbps VBR avec métadonnées et miniature intégrées",
            "Zéro pub, zéro popup, zéro redirection — l'interface la plus propre du web",
            "Pas d'inscription, pas de compte, pas de cookies de tracking",
            "Conversion ultra-rapide avec téléchargement parallèle",
            "Open source : le code est public, vérifiable, auditable",
            "Fonctionne sur mobile, tablette et desktop",
        ],
        "extra_content": """
            <h2>Quels formats YouTube sont supportés ?</h2>
            <p>ytbmp3 supporte tous les formats YouTube : vidéos classiques, Shorts, lives (replay), playlists (vidéo par vidéo). La conversion extrait la piste audio en qualité maximale quel que soit le format source.</p>
            <h2>YouTube MP3 sans pub : pourquoi c'est possible ?</h2>
            <p>ytbmp3 est un projet open source, pas une entreprise. Pas de serveurs à financer par la pub. Tu l'héberges toi-même ou tu utilises l'instance publique. Gratuit pour toujours.</p>
        """,
    },
    "instagram-mp3": {
        "platform_name": "Instagram",
        "title": "Convertir Instagram en MP3 Gratuit — Reels, Stories, Posts | ytbmp3",
        "h1": "Convertir Instagram en MP3",
        "description": "Télécharge et convertis les Reels Instagram, stories et posts vidéo en MP3. Gratuit, sans pub, sans inscription. Colle le lien Instagram, récupère le MP3.",
        "keywords": "instagram mp3, insta mp3, reel instagram mp3, convertir instagram mp3, telecharger reel instagram, instagram to mp3, download instagram audio, instagram reel mp3 converter",
        "lead": "Extrais l'audio de n'importe quel Reel, Story ou post vidéo Instagram en MP3 haute qualité. Gratuit et sans pub.",
        "points": [
            "Supporte les Reels, Stories, posts vidéo et IGTV",
            "Extraction audio en qualité maximale",
            "Pas besoin de compte Instagram pour convertir",
            "Aucune app à installer — tout se fait dans le navigateur",
            "Gratuit, sans pub, open source",
        ],
        "extra_content": """
            <h2>Comment récupérer le lien d'un Reel Instagram ?</h2>
            <p>Ouvre le Reel dans l'app Instagram, appuie sur les 3 points (⋯) puis "Copier le lien". Colle ce lien dans ytbmp3. Ça marche aussi depuis Instagram sur navigateur web.</p>
        """,
    },
    "tiktok-mp3": {
        "platform_name": "TikTok",
        "title": "Convertir TikTok en MP3 Gratuit — Télécharger Audio TikTok | ytbmp3",
        "h1": "Convertir TikTok en MP3",
        "description": "Convertis n'importe quelle vidéo TikTok en MP3 gratuitement. Sans pub, sans watermark audio. Colle le lien TikTok, télécharge le son en MP3.",
        "keywords": "tiktok mp3, tiktok to mp3, convertir tiktok mp3, telecharger son tiktok, tiktok audio download, tiktok mp3 converter, download tiktok sound mp3",
        "lead": "Récupère le son de n'importe quelle vidéo TikTok en MP3. Sans watermark, sans pub, qualité maximale.",
        "points": [
            "Audio sans watermark TikTok — son propre et net",
            "Fonctionne avec tous les liens TikTok (partage, navigateur)",
            "Qualité audio maximale extraite directement",
            "Pas d'app à installer, pas de compte requis",
            "100% gratuit et open source",
        ],
        "extra_content": """
            <h2>L'audio est-il sans le watermark TikTok ?</h2>
            <p>ytbmp3 extrait la piste audio originale de la vidéo TikTok. Le résultat est un MP3 propre, sans la voix "TikTok" ni watermark audio.</p>
        """,
    },
    "twitter-mp3": {
        "platform_name": "Twitter / X",
        "title": "Convertir Twitter/X en MP3 Gratuit — Vidéos et Spaces | ytbmp3",
        "h1": "Convertir Twitter / X en MP3",
        "description": "Convertis les vidéos Twitter/X et Spaces en MP3 gratuitement. Sans pub, qualité max. Colle le lien du tweet, télécharge l'audio en MP3.",
        "keywords": "twitter mp3, twitter to mp3, x mp3, convertir twitter mp3, telecharger video twitter mp3, twitter spaces mp3, download twitter video audio, x.com mp3 converter",
        "lead": "Extrais l'audio des vidéos et Spaces Twitter/X en MP3. Gratuit, sans pub, sans inscription.",
        "points": [
            "Supporte les vidéos de tweets et les Twitter Spaces",
            "Extraction audio directe, qualité maximale",
            "Fonctionne avec les liens twitter.com et x.com",
            "Aucune inscription requise",
            "Gratuit et open source",
        ],
        "extra_content": """
            <h2>Vidéos Twitter vs Twitter Spaces</h2>
            <p>ytbmp3 gère les deux types de contenu audio sur Twitter/X. Les <strong>vidéos de tweets</strong> sont converties en extrayant la piste audio du fichier vidéo. Les <strong>Twitter Spaces</strong> (conversations audio en direct) peuvent être téléchargés après leur diffusion si l'enregistrement est activé par l'hôte.</p>
            <h2>twitter.com ou x.com ?</h2>
            <p>Les deux fonctionnent. Que tu copies un lien depuis twitter.com ou x.com, ytbmp3 reconnaît automatiquement la plateforme et extrait l'audio. Tu peux aussi coller un lien mobile (t.co raccourci).</p>
        """,
    },
    "soundcloud-mp3": {
        "platform_name": "SoundCloud",
        "title": "Télécharger SoundCloud en MP3 Gratuit — Tracks et Playlists | ytbmp3",
        "h1": "Télécharger SoundCloud en MP3",
        "description": "Télécharge n'importe quel track SoundCloud en MP3 gratuitement. Sans pub, qualité originale. Colle le lien SoundCloud, récupère le MP3.",
        "keywords": "soundcloud mp3, soundcloud to mp3, telecharger soundcloud mp3, soundcloud downloader, soundcloud mp3 converter, download soundcloud free mp3, soundcloud gratuit",
        "lead": "Télécharge n'importe quel morceau SoundCloud en MP3 haute qualité. Gratuit, sans pub, sans limite.",
        "points": [
            "Télécharge en qualité originale (jusqu'à 320 kbps)",
            "Métadonnées et artwork intégrés automatiquement",
            "Fonctionne avec les tracks, sets et playlists",
            "Pas de compte SoundCloud Go requis pour télécharger",
            "Gratuit, open source, sans tracking",
        ],
        "extra_content": """
            <h2>Qualité audio SoundCloud</h2>
            <p>SoundCloud stocke les fichiers audio en plusieurs qualités. ytbmp3 récupère automatiquement le flux de la meilleure qualité disponible (128 kbps en streaming, 256 kbps HQ quand disponible) et le convertit en MP3. Les métadonnées (titre, artiste, artwork) sont intégrées dans le fichier MP3.</p>
            <h2>SoundCloud Go nécessaire ?</h2>
            <p>Non. ytbmp3 télécharge les morceaux publics sans abonnement SoundCloud Go. Si un morceau est marqué comme privé ou réservé aux abonnés, le lien ne fonctionnera pas — ytbmp3 ne contourne pas les restrictions d'accès.</p>
        """,
    },
    "facebook-mp3": {
        "platform_name": "Facebook",
        "title": "Convertir Facebook en MP3 Gratuit — Vidéos, Reels, Lives | ytbmp3",
        "h1": "Convertir Facebook en MP3",
        "description": "Convertis les vidéos Facebook, Reels et Lives en MP3 gratuitement. Sans pub, sans inscription. Colle le lien Facebook, télécharge l'audio.",
        "keywords": "facebook mp3, facebook to mp3, convertir video facebook mp3, telecharger video facebook mp3, facebook reels mp3, facebook live mp3, download facebook video audio",
        "lead": "Extrais l'audio de n'importe quelle vidéo, Reel ou Live Facebook en MP3. Gratuit et sans pub.",
        "points": [
            "Supporte les vidéos de fil d'actualité, Reels, Stories et Lives",
            "Extraction audio directe, qualité maximale",
            "Fonctionne avec les liens facebook.com et fb.watch",
            "Les vidéos publiques n'ont pas besoin de connexion",
            "Gratuit, sans pub, open source",
        ],
        "extra_content": """
            <h2>Comment copier le lien d'une vidéo Facebook ?</h2>
            <p>Sur mobile : appuie sur les 3 points (⋯) en haut à droite de la vidéo, puis "Copier le lien". Sur desktop : clique droit sur la vidéo > "Copier l'URL de la vidéo". Colle ensuite ce lien dans ytbmp3.</p>
            <h2>Vidéos Facebook privées</h2>
            <p>ytbmp3 ne peut convertir que les vidéos Facebook publiques. Si la vidéo est en accès restreint (amis uniquement, groupe privé), le lien ne fonctionnera pas. Cela protège la vie privée des utilisateurs.</p>
        """,
    },
    "dailymotion-mp3": {
        "platform_name": "Dailymotion",
        "title": "Convertir Dailymotion en MP3 Gratuit — Vidéos et Chaînes | ytbmp3",
        "h1": "Convertir Dailymotion en MP3",
        "description": "Convertis les vidéos Dailymotion en MP3 gratuitement. Sans pub, qualité max. Colle le lien Dailymotion, télécharge l'audio en MP3.",
        "keywords": "dailymotion mp3, dailymotion to mp3, convertir dailymotion mp3, telecharger dailymotion mp3, dailymotion converter, dailymotion audio download",
        "lead": "Convertis n'importe quelle vidéo Dailymotion en MP3 haute qualité. Gratuit, sans pub, sans inscription.",
        "points": [
            "Supporte toutes les vidéos Dailymotion publiques",
            "Extraction audio en qualité maximale (320 kbps)",
            "Métadonnées intégrées automatiquement",
            "Pas d'inscription ni de compte requis",
            "Gratuit et open source",
            "Plateforme française — optimisé pour le contenu francophone",
        ],
        "extra_content": """
            <h2>Pourquoi Dailymotion ?</h2>
            <p>Dailymotion est la plus grande plateforme vidéo française et européenne. Elle héberge du contenu exclusif (émissions TV, documentaires, clips) qui n'est pas disponible sur YouTube. ytbmp3 extrait l'audio en qualité maximale, idéal pour les podcasts, interviews et musique francophone.</p>
        """,
    },
    "convertir-fichier-mp3": {
        "platform_name": "Fichier local",
        "title": "Convertir Fichier Vidéo en MP3 Gratuit — MP4, WEBM, MKV, WAV | ytbmp3",
        "h1": "Convertir un fichier local en MP3",
        "description": "Convertis tes fichiers vidéo et audio locaux en MP3 : MP4, WEBM, MKV, WAV, OGG, FLAC, AVI. Glisse-dépose dans le navigateur. Gratuit, sans upload serveur.",
        "keywords": "convertir fichier mp3, convertir video mp3, mp4 to mp3, webm to mp3, mkv to mp3, wav to mp3, convertir fichier audio, conversion mp3 en ligne gratuit, screencast mp3",
        "lead": "Convertis tes fichiers vidéo et audio en MP3 directement dans ton navigateur. MP4, WEBM, MKV, WAV, OGG, FLAC — tout passe.",
        "points": [
            "Glisse-dépose : drag & drop dans le navigateur",
            "Tous les formats : MP4, WEBM, MKV, AVI, MOV, WAV, OGG, FLAC, WMA",
            "Idéal pour les screencasts Ubuntu, captures d'écran vidéo",
            "Qualité audio maximale (320 kbps VBR)",
            "Pas de limite de taille (jusqu'à 500 Mo)",
            "Gratuit, sans pub, open source",
        ],
        "extra_content": """
            <h2>Convertir un screencast Ubuntu en MP3</h2>
            <p>Les screencasts Ubuntu (enregistrements d'écran) sont sauvegardés en WEBM dans ~/Videos/Screencasts/. Pour les convertir en MP3, ouvre ytbmp3, va dans l'onglet "Fichier local" et glisse le fichier .webm. L'audio est extrait automatiquement en MP3 haute qualité.</p>
            <h2>Formats supportés</h2>
            <p>ytbmp3 utilise <strong>ffmpeg</strong> pour la conversion de fichiers locaux. Cela signifie que presque tous les formats vidéo et audio sont supportés : MP4, WEBM, MKV, AVI, MOV, FLV, WMV, WAV, OGG, FLAC, AAC, WMA, AIFF, M4A, OPUS et bien d'autres.</p>
            <h2>Quelle est la limite de taille ?</h2>
            <p>ytbmp3 accepte les fichiers jusqu'à 500 Mo. Pour les fichiers plus volumineux (films, conférences longues), il est recommandé de les découper avant conversion ou d'utiliser la version ligne de commande (ytbmp3.sh).</p>
        """,
    },
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/<slug>")
def platform_page(slug):
    page = PLATFORMS.get(slug)
    if not page:
        return render_template("404.html", platforms=PLATFORMS), 404
    return render_template("platform.html", **page, platforms=PLATFORMS)


def start(target, *args, **task):
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {"status": "queued", **task}
    threading.Thread(target=target, args=(task_id, *args), daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/convert/url", methods=["POST"])
def api_convert_url():
    url = request.get_json().get("url", "").strip()
    if not url:
        return jsonify({"error": "URL manquante"}), 400
    return start(convert_url, url, type="url", source=url)


@app.route("/convert/file", methods=["POST"])
def api_convert_file():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"error": "Fichier vide"}), 400

    # never trust the client's filename on disk
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{Path(upload.filename).suffix}"
    upload.save(path)
    return start(convert_file, path, type="file", source=upload.filename)


@app.route("/status/<task_id>")
def api_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Tâche inconnue"}), 404
    return jsonify(task)


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.route("/library")
def library():
    mp3s = sorted(OUTPUT_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonify([
        {"name": p.name, "size_mb": round(p.stat().st_size / (1024 * 1024), 1)}
        for p in mp3s
    ])


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html", platforms=PLATFORMS), 404


@app.route("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    content = f"""User-agent: *
Allow: /
Disallow: /convert/
Disallow: /status/
Disallow: /download/
Disallow: /library
Disallow: /uploads/

Sitemap: {base}/sitemap.xml
"""
    return Response(content, mimetype="text/plain")


LASTMOD = "2026-03-28"  # bump by hand on deploy


@app.route("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    urls = [{"loc": base + "/", "priority": "1.0", "changefreq": "weekly"}]
    urls += [{"loc": f"{base}/{slug}", "priority": "0.8", "changefreq": "monthly"} for slug in PLATFORMS]

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f"""  <url>
    <loc>{u["loc"]}</loc>
    <lastmod>{LASTMOD}</lastmod>
    <changefreq>{u["changefreq"]}</changefreq>
    <priority>{u["priority"]}</priority>
  </url>\n"""
    xml += '</urlset>'
    return Response(xml, mimetype="application/xml")


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "ytbmp3 — Convertisseur MP3 Gratuit",
        "short_name": "ytbmp3",
        "description": "Convertis YouTube, Instagram, TikTok et +1000 sites en MP3. Gratuit, sans pub, pour toujours.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#06060a",
        "theme_color": "#06060a",
        "categories": ["utilities", "music"],
        "lang": "fr",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
