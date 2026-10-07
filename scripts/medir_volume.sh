#!/usr/bin/env bash
# Gera a Curitiba sintética e roda o pipeline inteiro medindo tempo e memória de cada etapa.
#   scripts/medir_volume.sh <dsn do banco descartável> <pasta de dados> [fator]
# O banco é zerado (schema cwb e dados_rfb). Resultado em <pasta>/medicao.tsv e relatorios/.
set -uo pipefail
DSN="${1:?dsn}"; DADOS="${2:?pasta}"; FATOR="${3:-1.0}"
PY="${PYTHON:-python}"
export PINEAL_DSN="$DSN" RFB_DSN="$DSN" PINEAL_DADOS="$DADOS" PINEAL_COMPETENCIA="2026-10"
mkdir -p "$DADOS"
psql "$DSN" -qc "DROP SCHEMA IF EXISTS cwb CASCADE" >/dev/null
OUT="$DADOS/medicao.tsv"; printf "etapa\tsegundos\tpico_mb\tsaida\n" > "$OUT"
medir() {
  local nome="$1"; shift
  "$PY" scripts/cronometro.py "$DADOS/.t" "$@" > "$DADOS/$nome.log" 2>&1
  local rc=$?
  read -r seg kb < "$DADOS/.t" || { seg=?; kb=0; }
  printf "%s\t%s\t%s\t%s\n" "$nome" "$seg" "$((kb / 1024))" "$rc" | tee -a "$OUT"
}
medir gerar "$PY" scripts/volume_sintetico.py --dados "$DADOS" --dsn "$DSN" --fator "$FATOR"
for e in schema setores ippuc cnefe cnpj geocodificar territorio; do medir "m0_$e" "$PY" -m etl.m0 --so "$e"; done
for e in alvaras seguranca transporte; do medir "m1_$e" "$PY" -m etl.m1 --so "$e"; done
medir m2_apoio "$PY" -m etl.m2 --so apoio
medir m2_censo "$PY" -m etl.m2 --so censo
for e in cruzamentos enriquecer indicadores score exportar; do medir "m2_$e" "$PY" -m etl.m2 --so "$e"; done
medir vias "$PY" -m etl.fontes.osm_vias
read -r LAT LON < <(psql "$DSN" -AtF' ' -c "SELECT ST_Y(c), ST_X(c) FROM (SELECT ST_Centroid(ST_Extent(geom)) c FROM cwb.bairro) x")
medir isocrona_pe "$PY" -m etl.isocronas --lat "$LAT" --lon "$LON" --minutos 10 15
medir isocrona_onibus "$PY" -m etl.isocronas --lat "$LAT" --lon "$LON" --modo onibus --minutos 20 --saida "2026-10-08 08:00"
medir publicar "$PY" -m etl.publicar --pasta "$DADOS/publicar"
cat "$OUT"
