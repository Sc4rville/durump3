#!/usr/bin/env bash
# ytbmp3 - Convertisseur YouTube → MP3 rapide
# Usage:
#   ./ytbmp3.sh URL [URL2 URL3 ...]
#   ./ytbmp3.sh -f fichier.txt          (un lien par ligne)

set -euo pipefail

YT_DLP="${YT_DLP:-$HOME/.local/bin/yt-dlp}"
OUT_DIR="${OUT_DIR:-$(pwd)/mp3}"

mkdir -p "$OUT_DIR"

download() {
    "$YT_DLP" \
        --extract-audio \
        --audio-format mp3 \
        --audio-quality 0 \
        --embed-thumbnail \
        --add-metadata \
        --no-playlist \
        --concurrent-fragments 4 \
        -o "$OUT_DIR/%(title)s.%(ext)s" \
        "$1"
}

if [[ $# -eq 0 ]]; then
    echo "Usage: ./ytbmp3.sh URL [URL2 ...]"
    echo "       ./ytbmp3.sh -f liens.txt"
    echo ""
    echo "Les MP3 sont sauvegardés dans: $OUT_DIR"
    exit 1
fi

if [[ "$1" == "-f" ]]; then
    if [[ ! -f "$2" ]]; then
        echo "Erreur: fichier '$2' introuvable"
        exit 1
    fi
    while IFS= read -r url; do
        [[ -z "$url" || "$url" == \#* ]] && continue
        echo ">>> $url"
        download "$url" || echo "ECHEC: $url"
    done < "$2"
else
    for url in "$@"; do
        echo ">>> $url"
        download "$url" || echo "ECHEC: $url"
    done
fi

echo ""
echo "Terminé ! Fichiers dans: $OUT_DIR"
