#!/bin/sh
# Se in /etc/nginx/certs non c'è un certificato, ne crea uno autofirmato.
# In sede si sostituisce con quello della CA interna (crm.crt e crm.key).
set -e
DIR=/etc/nginx/certs
mkdir -p "$DIR"
if [ ! -f "$DIR/crm.crt" ] || [ ! -f "$DIR/crm.key" ]; then
  NOME="${CRM_HOSTNAME:-crm.local}"
  echo "Creo un certificato autofirmato per $NOME"
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$DIR/crm.key" -out "$DIR/crm.crt" \
    -subj "/CN=$NOME" -addext "subjectAltName=DNS:$NOME,DNS:localhost,IP:127.0.0.1" 2>/dev/null
fi
