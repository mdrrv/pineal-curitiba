#!/usr/bin/env bash
# Junta as camadas .fgb de um pacote de publicação (python -m etl.publicar) num PMTiles para o MapLibre.
# Requer tippecanoe 2.17+ (lê FlatGeobuf e grava PMTiles): https://github.com/felt/tippecanoe
#   scripts/pmtiles.sh dados/publicar/2026-10-07
set -euo pipefail
pasta="${1:?uso: scripts/pmtiles.sh <pasta do pacote>}"
command -v tippecanoe >/dev/null || { echo "tippecanoe não instalado (brew install tippecanoe / compilar do GitHub)"; exit 1; }
camadas=()
for f in "$pasta"/*.fgb; do
  [ -e "$f" ] || continue
  nome="$(basename "$f" .fgb)"
  camadas+=(-L "$nome:$f")
done
[ ${#camadas[@]} -gt 0 ] || { echo "nenhum .fgb em $pasta"; exit 1; }
# zoom 10 a 16: cidade inteira até a quadra; pontos de empresa só a partir do 13 para não pesar
tippecanoe -o "$pasta/pineal.pmtiles" --force -Z10 -z16 --drop-densest-as-needed --extend-zooms-if-still-dropping \
  --attribution "MINDATA; IBGE; Prefeitura de Curitiba (CC BY 4.0); © colaboradores do OpenStreetMap" \
  "${camadas[@]}"
echo "ok: $pasta/pineal.pmtiles"
