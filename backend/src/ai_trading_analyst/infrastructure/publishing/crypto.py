"""Zero-Knowledge fuer den Datenbaum -- die Serverhaelfte (ADR 0060, Stufe 2).

Der Anbieter, bei dem der Datenbaum liegt, soll Chiffrat sehen und sonst
nichts: keine Kurse, keine Berichte, keine Symbole, nicht einmal die
Dateinamen. Entschluesselt wird ausschliesslich im Browser des Inhabers, mit
einer Passphrase, die den Server nie in Richtung Anbieter verlaesst.

**Das Verfahren ist Eigenschaft des Builds, nicht des Manifests.** Der
Klartextkopf ``data/manifest.head.json`` nennt Salt und Iterationszahl,
damit der Browser den Schluessel ableiten kann -- er nennt **nicht**, ob
verschluesselt wurde. Eine Oberflaeche, die aus dem Kopf lernt, sie duerfe
Klartext annehmen, waere mit einem Schreibzugriff auf eine einzige Datei
wieder abzuschalten (Bedrohung T21).

Die Wahl der Bausteine folgt dem, was ``WebCrypto`` im Browser ohne
Fremdbibliothek kann: PBKDF2-HMAC-SHA256 zur Ableitung, AES-256-GCM je
Datei, HMAC-SHA256 fuer die opaken Namen. Kein Argon2, so gern man es haette
-- es waere im Browser eine Bibliothek, die jemand ausliefern und pflegen
muesste, und der Angreifer, gegen den die Iterationszahl steht, hat hier
ohnehin nur ein Chiffrat und keinen Anmeldeversuch.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import os
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MINDEST_ITERATIONEN = 600_000
"""Untergrenze der PBKDF2-Runden (ADR 0060, Entscheidung Punkt 6).

Der Browser erzwingt sie ein zweites Mal -- und wogegen das wirkt, ist genau
zu benennen. **Nicht** gegen jemanden, der den Klartextkopf umschreibt: Der
Arbeitsfaktor des gespeicherten Chiffrats steht fest, sobald hier
verschluesselt wurde; wer nur den Kopf aendert, erreicht eine falsche
Ableitung und damit einen Ausfall. Wohl aber gegen **diese Seite**: gegen
eine Konfiguration, die zu niedrig gesetzt wurde, und gegen eine aeltere
Fassung des Exporters. Die Pruefung im Browser steht deshalb dort, wo der
Server sie nicht abschalten kann.
"""

SCHLUESSELLAENGE = 32
NONCE_LAENGE = 12
"""Zwoelf Byte -- die Laenge, fuer die GCM entworfen ist. Laengere Nonces
werden intern gehasht und verschenken die Kollisionsfreiheit."""

_KDF = "PBKDF2-HMAC-SHA256"
_CIPHER = "AES-256-GCM"

_LABEL_INHALT = b"ata-export-enc-v1"
_LABEL_NAMEN = b"ata-export-name-v1"

_LAENGENFELD = struct.Struct(">I")
"""Vier Byte vor dem komprimierten Inhalt: seine wahre Laenge.

Ohne sie waere die Auffuellung auf Groessenklassen nicht mehr von Inhalt zu
unterscheiden -- gzip endet nicht an einer erkennbaren Marke, und ein
Entpacker, der Nullbytes mitliest, scheitert an einer Datei, die in
Wahrheit heil ist.
"""


class KryptoKonfigurationError(RuntimeError):
    """Die Vorgaben der Verschluesselung sind nicht erfuellt."""


@dataclass(frozen=True, slots=True)
class Exportschluessel:
    """Zwei getrennte Schluessel aus einer Passphrase.

    Getrennt, weil derselbe Schluessel fuer Verschluesselung und Namensbildung
    zwei Aufgaben mit einem Geheimnis erledigte: Wer je einen Namen und den
    zugehoerigen Pfad kennt, haette damit ein Orakel gegen den Inhalt.
    """

    inhalt: bytes
    namen: bytes


def leite_schluessel_ab(passphrase: str, salt: bytes, iterationen: int) -> Exportschluessel:
    """PBKDF2 einmal, danach zwei getrennte Schluessel per HMAC.

    Nur **eine** teure Ableitung: PBKDF2 zweimal zu rechnen kostete die
    doppelte Zeit auf dem Server und im Browser, ohne die Sicherheit zu
    erhoehen -- die Trennung leistet das HMAC danach.
    """
    if iterationen < MINDEST_ITERATIONEN:
        raise KryptoKonfigurationError(
            f"Mindestens {MINDEST_ITERATIONEN} Iterationen verlangt, {iterationen} eingestellt."
        )
    if len(salt) < 16:
        raise KryptoKonfigurationError("Das Salt braucht mindestens 16 Byte.")
    if not passphrase:
        raise KryptoKonfigurationError("Ohne Passphrase keine Verschluesselung.")
    stamm = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, iterationen, SCHLUESSELLAENGE
    )
    return Exportschluessel(
        inhalt=hmac.digest(stamm, _LABEL_INHALT, "sha256"),
        namen=hmac.digest(stamm, _LABEL_NAMEN, "sha256"),
    )


def groessenklasse(laenge: int) -> int:
    """Die naechste Zweierpotenz, mindestens 1 KiB.

    Der Anbieter sieht die Dateigroesse, ob man will oder nicht. Ohne
    Auffuellung saehe er damit, welche Aktie viele Berichte hat und welche
    keinen -- ueber Wochen hinweg ein brauchbares Profil. Die Auffuellung
    macht daraus eine Groessenklasse.

    Zweierpotenzen und keine feinere Leiter: Sie kosten im Mittel rund die
    Haelfte an Volumen und lassen dafuer nur den Zweierlogarithmus durch.
    """
    klasse = 1024
    while klasse < laenge:
        klasse *= 2
    return klasse


def packe(klartext: bytes) -> bytes:
    """Komprimieren und auf eine Groessenklasse auffuellen.

    Das Ergebnis ist genau das, was verschluesselt wird -- und genau das, was
    der Browser nach dem Entschluesseln vorfindet. Diese Funktion ist deshalb
    die **Formatdefinition** und keine Interna: Wer sie aendert, aendert das,
    was die Gegenseite lesen koennen muss.

    ``mtime=0`` in gzip: Ohne das stuende der Zeitpunkt im Kopf jeder Datei,
    und zwei Exporte desselben Inhalts ergaeben verschiedene Bytes -- der
    Vergleich am Klartext bliebe zwar richtig, aber jede Datei traege eine
    Zeitangabe nach draussen, die niemand gebraucht hat.
    """
    gepackt = gzip.compress(klartext, compresslevel=9, mtime=0)
    roh = _LAENGENFELD.pack(len(gepackt)) + gepackt
    return roh.ljust(groessenklasse(len(roh)), b"\x00")


def entpacke(gefuellt: bytes) -> bytes:
    """Die Gegenrichtung zu ``packe``."""
    (laenge,) = _LAENGENFELD.unpack(gefuellt[: _LAENGENFELD.size])
    anfang = _LAENGENFELD.size
    return gzip.decompress(gefuellt[anfang : anfang + laenge])


class Verschluesselung:
    """Verschluesselt einzelne Dateien des Datenbaums.

    ``baum_id`` bindet jede Datei an **diesen** Datenbaum: Sie steht in den
    Zusatzdaten und laesst sich nicht faelschen, ohne dass die Entschluesselung
    scheitert. Eine Datei aus einem anderen Baum -- etwa dem einer frueheren
    Passphrase oder einem untergeschobenen -- ist damit unbrauchbar.

    **Warum die Kennung des Datenbaums und nicht die des einzelnen Exports**,
    obwohl der Spike-Bericht letzteres vorsah: Eine Export-Kennung in den
    Zusatzdaten zwaenge dazu, bei jedem Lauf **jede** Datei neu zu
    verschluesseln und hochzuladen -- auch die zweihundert Charts, an denen
    sich nichts geaendert hat. Was die Export-Kennung leisten sollte, naemlich
    das Einspielen einer Datei aus einem anderen Stand, leistet stattdessen
    das Manifest: Es traegt je Pfad den Hash des Klartexts, wird bei jedem
    Export neu geschrieben und im Browser geprueft. Gegen das Zurueckspielen
    des **ganzen** Standes half die Export-Kennung ohnehin nicht; dagegen
    hilft nur, dass die Oberflaeche den Stand anzeigt.
    """

    def __init__(self, schluessel: Exportschluessel, *, baum_id: str, format_version: int) -> None:
        self._aead = AESGCM(schluessel.inhalt)
        self._namensschluessel = schluessel.namen
        self._baum_id = baum_id
        self._format = format_version

    def dateiname(self, pfad: str) -> str:
        """Ein opaker, aber stabiler Name fuer einen Pfad des Datenbaums.

        Stabil, damit ein unveraenderter Chart beim naechsten Lauf nicht als
        neue Datei erscheint; opak, damit der Anbieter aus dem Namen weder
        Symbol noch Art der Datei lesen kann. Beides zugleich geht nur ueber
        eine schluesselgebundene Funktion -- ein blosser Hash des Pfades waere
        fuer jeden nachrechenbar, der die Pfadstruktur kennt, und die steht
        im oeffentlichen Repository.
        """
        return hmac.new(self._namensschluessel, pfad.encode("utf-8"), "sha256").hexdigest()[:32]

    def _zusatzdaten(self, pfad: str) -> bytes:
        """Format, Baumkennung und Pfad, durch Zeilenumbrueche getrennt.

        Die Trennung muss **eindeutig** sein: Enthielte eine Kennung oder ein
        Pfad selbst einen Zeilenumbruch, ergaeben zwei verschiedene Tripel
        dieselben Zusatzdaten, und die Bindung an den Pfad waere dort
        aufgehoben. Heute kann das nicht vorkommen -- die Kennung ist eine
        UUID, und ``dateisicherer_name`` laesst nur Buchstaben, Ziffern,
        ``_`` und ``-`` durch. Erzwungen war es bisher trotzdem nirgends, und
        eine Eigenschaft, auf der die Sicherheit steht, sollte keine blosse
        Beobachtung sein.
        """
        if "\n" in self._baum_id or "\n" in pfad:
            raise KryptoKonfigurationError(
                "Zeilenumbruch in Baumkennung oder Pfad -- die Zusatzdaten waeren mehrdeutig."
            )
        return f"{self._format}\n{self._baum_id}\n{pfad}".encode()

    def verschluessele(self, pfad: str, klartext: bytes) -> bytes:
        """Komprimieren, auffuellen, verschluesseln -- in dieser Reihenfolge.

        Komprimieren **vor** dem Verschluesseln, weil Chiffrat sich nicht mehr
        komprimieren laesst. Auffuellen dazwischen, damit die Groesse des
        Chiffrats nichts mehr ueber die des Inhalts sagt.
        """
        nonce = os.urandom(NONCE_LAENGE)
        gefuellt = packe(klartext)
        return nonce + self._aead.encrypt(nonce, gefuellt, self._zusatzdaten(pfad))

    def entschluessele(self, pfad: str, chiffrat: bytes) -> bytes:
        """Die Gegenrichtung -- gebraucht von den Tests und vom Notfallwerkzeug.

        Der Browser macht dasselbe mit WebCrypto. Dass es hier steht, ist die
        Probe darauf, dass beide Seiten dasselbe Format meinen.
        """
        nonce, rest = chiffrat[:NONCE_LAENGE], chiffrat[NONCE_LAENGE:]
        return entpacke(self._aead.decrypt(nonce, rest, self._zusatzdaten(pfad)))


def kopf(
    *, salt: bytes, iterationen: int, format_version: int, baum_id: str, manifest: str
) -> bytes:
    """Der Klartextkopf ``data/manifest.head.json``.

    Er enthaelt genau das, was der Browser braucht, **bevor** er
    entschluesseln kann, und keinen Schalter, der etwas abschalten koennte.
    Die Angaben zu Verfahren und Runden stehen darin, damit der Browser sie
    **pruefen** kann -- nicht, damit er ihnen folgt.
    """
    return json.dumps(
        {
            "format": format_version,
            "kdf": _KDF,
            "iterations": iterationen,
            "salt": salt.hex(),
            "cipher": _CIPHER,
            "tree_id": baum_id,
            "manifest": manifest,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
