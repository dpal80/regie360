"""Invio delle e-mail con Microsoft 365, tramite un'app registrata in Entra ID (Microsoft Graph).

L'app entra con le proprie credenziali (tenant, ID applicazione, segreto) e spedisce dalla casella
scelta come mittente. In Entra ID le serve il permesso applicativo Mail.Send con consenso dell'amministratore.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Impostazione
from app.segreti import decifra

log = logging.getLogger(__name__)

IMPOSTAZIONE_M365 = "microsoft365"
ACCESSO = "https://login.microsoftonline.com"
GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = 15


class PostaNonConfigurata(Exception):
    pass


class PostaNonInviata(Exception):
    """Microsoft ha rifiutato l'accesso o l'invio: il messaggio spiega cosa controllare."""


@dataclass
class ConfigPosta:
    attivo: bool = False
    tenant_id: str = ""
    client_id: str = ""
    mittente: str = ""  # la casella da cui partono le e-mail
    segreto: str | None = None

    @property
    def configurato(self) -> bool:
        return bool(self.attivo and self.tenant_id and self.client_id and self.mittente and self.segreto)


def config_posta(db: Session) -> ConfigPosta:
    salvata = db.get(Impostazione, IMPOSTAZIONE_M365)
    if salvata is None:
        return ConfigPosta()
    v = salvata.valore
    return ConfigPosta(
        attivo=bool(v.get("attivo", False)),
        tenant_id=v.get("tenant_id", ""),
        client_id=v.get("client_id", ""),
        mittente=v.get("mittente", ""),
        segreto=decifra(v.get("segreto_cifrato")),
    )


def _richiesta(url: str, *, dati: bytes, intestazioni: dict[str, str]) -> dict:
    richiesta = urllib.request.Request(url, method="POST", data=dati, headers=intestazioni)
    try:
        with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
            corpo = risposta.read(1_000_000)
    except urllib.error.HTTPError as exc:
        try:
            errore = json.loads(exc.read(100_000))
        except ValueError:
            errore = {}
        dettaglio = errore.get("error_description") or (errore.get("error") or {})
        if isinstance(dettaglio, dict):
            dettaglio = dettaglio.get("message", "")
        raise PostaNonInviata(f"Microsoft ha risposto {exc.code}. {str(dettaglio).splitlines()[0] if dettaglio else ''}".strip()) from None
    except (urllib.error.URLError, OSError) as exc:
        raise PostaNonInviata(f"Microsoft 365 non raggiungibile: {getattr(exc, 'reason', exc)}") from None
    try:
        return json.loads(corpo) if corpo else {}
    except ValueError:
        return {}


def invia_mail(cfg: ConfigPosta, destinatari: list[str], oggetto: str, testo: str) -> None:
    """Spedisce un'e-mail di solo testo dalla casella mittente."""
    if not cfg.configurato:
        raise PostaNonConfigurata()
    token = _richiesta(
        f"{ACCESSO}/{urllib.parse.quote(cfg.tenant_id)}/oauth2/v2.0/token",
        dati=urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": cfg.client_id,
            "client_secret": cfg.segreto,
            "scope": "https://graph.microsoft.com/.default",
        }).encode(),
        intestazioni={"Content-Type": "application/x-www-form-urlencoded"},
    ).get("access_token")
    if not token:
        raise PostaNonInviata("Microsoft non ha rilasciato l'accesso: controlla tenant, ID applicazione e segreto")
    messaggio = {
        "message": {
            "subject": oggetto,
            "body": {"contentType": "Text", "content": testo},
            "toRecipients": [{"emailAddress": {"address": d}} for d in destinatari],
        },
        "saveToSentItems": True,
    }
    _richiesta(
        f"{GRAPH}/users/{urllib.parse.quote(cfg.mittente)}/sendMail",
        dati=json.dumps(messaggio).encode(),
        intestazioni={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    log.info("E-mail inviata a %d destinatari", len(destinatari))


def invia_credenziali(cfg: ConfigPosta, email: str, nome: str, username: str, password: str) -> None:
    invia_mail(cfg, [email], "Regie360: le tue credenziali", (
        f"Ciao {nome},\n\n"
        "è stato creato il tuo accesso a Regie360, il CRM di REGIE AUTO.\n\n"
        f"Nome utente: {username}\n"
        f"Password provvisoria: {password}\n\n"
        "Al primo accesso ti verrà chiesto di scegliere una nuova password. "
        "Ti consigliamo anche di attivare la verifica in due passaggi dalla pagina «Il mio account»."
    ))


def invia_nuova_password(cfg: ConfigPosta, email: str, nome: str, username: str, password: str) -> None:
    invia_mail(cfg, [email], "Regie360: nuova password provvisoria", (
        f"Ciao {nome},\n\n"
        "la tua password di Regie360 è stata reimpostata da un amministratore.\n\n"
        f"Nome utente: {username}\n"
        f"Password provvisoria: {password}\n\n"
        "Al prossimo accesso ti verrà chiesto di sceglierne una nuova."
    ))


def invia_codice_reset(cfg: ConfigPosta, email: str, nome: str, codice: str, minuti: int) -> None:
    invia_mail(cfg, [email], "Regie360: codice per reimpostare la password", (
        f"Ciao {nome},\n\n"
        "hai chiesto di reimpostare la password di Regie360.\n\n"
        f"Codice: {codice}\n\n"
        f"Vale {minuti} minuti e si usa una volta sola: inseriscilo nella pagina di accesso insieme alla nuova password.\n"
        "Se non sei stato tu, ignora questa e-mail: la password resta quella di prima."
    ))
