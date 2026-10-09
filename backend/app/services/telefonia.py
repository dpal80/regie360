"""Collegamento a NethVoice: token di Phone Island e dati SIP di ogni operatore.

Il CRM entra nella CTI di NethVoice con le credenziali dell'operatore, chiede il token per
Phone Island e l'interno WebRTC, e conserva il risultato cifrato: così non serve rigenerare il
token a ogni accesso (NethVoice ne tiene uno solo per utente, e uno nuovo revoca il precedente).
"""

import base64
import json
import logging
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Impostazione, Utente
from app.segreti import cifra, decifra

log = logging.getLogger(__name__)

IMPOSTAZIONE_NETHVOICE = "nethvoice"
TIMEOUT = 8


class NethVoiceNonRaggiungibile(Exception):
    pass


class CredenzialiRifiutate(Exception):
    pass


class SenzaInternoWeb(Exception):
    """L'utente esiste su NethVoice ma non ha un interno WebRTC (telefono web)."""


@dataclass
class ConfigNethVoice:
    attivo: bool = False
    cti_host: str = ""  # nome con cui i PC raggiungono la CTI di NethVoice, es. cti.regieauto.local
    sip_host: str = ""
    sip_porta: str = ""
    certificato_ca: str = ""  # certificato della CA interna in formato PEM, se serve

    @property
    def configurato(self) -> bool:
        return bool(self.attivo and self.cti_host and self.sip_host and self.sip_porta)


def config_nethvoice(db: Session) -> ConfigNethVoice:
    salvata = db.get(Impostazione, IMPOSTAZIONE_NETHVOICE)
    if salvata is None:
        return ConfigNethVoice()
    v = salvata.valore
    return ConfigNethVoice(
        attivo=bool(v.get("attivo", False)),
        cti_host=v.get("cti_host", ""),
        sip_host=v.get("sip_host", ""),
        sip_porta=str(v.get("sip_porta", "")),
        certificato_ca=v.get("certificato_ca", ""),
    )


def _chiama(cfg: ConfigNethVoice, metodo: str, percorso: str, *, token: str | None = None,
            dati: dict | None = None) -> dict:
    contesto = ssl.create_default_context(cadata=cfg.certificato_ca or None)
    richiesta = urllib.request.Request(
        f"https://{cfg.cti_host}/api{percorso}",
        method=metodo,
        data=json.dumps(dati).encode() if dati is not None else None,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    if token:
        richiesta.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(richiesta, timeout=TIMEOUT, context=contesto) as risposta:
            corpo = risposta.read(1_000_000)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise CredenzialiRifiutate() from None
        raise NethVoiceNonRaggiungibile(f"risposta {exc.code} da {percorso}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise NethVoiceNonRaggiungibile(str(getattr(exc, "reason", exc))) from None
    try:
        return json.loads(corpo) if corpo else {}
    except ValueError:
        raise NethVoiceNonRaggiungibile(f"risposta non valida da {percorso}") from None


def ottieni_telefono(cfg: ConfigNethVoice, username: str, password: str) -> dict:
    """Entra in NethVoice come l'operatore e restituisce i dati per Phone Island."""
    if not cfg.configurato:
        raise NethVoiceNonRaggiungibile("NethVoice non configurato")
    sessione = _chiama(cfg, "POST", "/login", dati={"username": username, "password": password}).get("token")
    if not sessione:
        raise CredenzialiRifiutate()
    try:
        io = _chiama(cfg, "GET", "/user/me", token=sessione)
        interni = (io.get("endpoints") or {}).get("extension") or []
        web = next((e for e in interni if e.get("type") == "webrtc" and e.get("id") and e.get("secret")), None)
        if web is None:
            raise SenzaInternoWeb()
        token = _chiama(cfg, "POST", "/tokens/persistent/phone-island", token=sessione).get("token")
        if not token:
            raise NethVoiceNonRaggiungibile("NethVoice non ha restituito il token per Phone Island")
    finally:
        try:
            _chiama(cfg, "POST", "/logout", token=sessione)
        except Exception:
            pass
    return {
        "cti_username": username,
        "cti_token": token,
        "sip_interno": str(web["id"]),
        "sip_password": str(web["secret"]),
    }


def salva_telefono(utente: Utente, telefono: dict) -> None:
    utente.telefono_cifrato = cifra(json.dumps(telefono))


def leggi_telefono(utente: Utente) -> dict | None:
    chiaro = decifra(utente.telefono_cifrato)
    return json.loads(chiaro) if chiaro else None


def data_config(cfg: ConfigNethVoice, telefono: dict) -> str:
    """La stringa che Phone Island si aspetta: sette campi separati da ':' in Base64."""
    campi = [
        cfg.cti_host, telefono["cti_username"], telefono["cti_token"], telefono["sip_interno"],
        telefono["sip_password"], cfg.sip_host, cfg.sip_porta,
    ]
    return base64.b64encode(":".join(campi).encode()).decode()


def collega_al_login(db: Session, utente: Utente, password: str) -> None:
    """Al login di un utente di dominio prova a collegare il telefono con le stesse credenziali.

    È un tentativo: se NethVoice non risponde o l'utente non ha il telefono web, il login va avanti.
    """
    cfg = config_nethvoice(db)
    if not cfg.configurato or leggi_telefono(utente) is not None:
        return
    try:
        salva_telefono(utente, ottieni_telefono(cfg, utente.username, password))
    except (NethVoiceNonRaggiungibile, CredenzialiRifiutate, SenzaInternoWeb) as exc:
        log.info("Telefono non collegato al login di %s: %s", utente.username, type(exc).__name__)


def solo_cifre(numero: str | None) -> str:
    return "".join(c for c in (numero or "") if c.isdigit())
