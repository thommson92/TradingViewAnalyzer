"""Der Ausgang fuer den Snapshot des Dashboards (ADR 0060, Entscheidung 2).

Der Server sendet; es gibt keinen Weg zurueck. Diese Klasse setzt den Port
``DashboardPublisher`` um und tut dabei genau drei Dinge: den Datenbaum
holen, ihn schreiben -- in Stufe 2 verschluesselt -- und den Zustand
fortschreiben, aus dem der naechste Lauf weiss, was sich geaendert hat.

**Der Datenbaum kommt als Aufzaehlung herein und nicht als Aufruf in die
Praesentationsschicht.** Die Infrastruktur darf sie nicht kennen (Doc 10,
Paragraph 9); verdrahtet wird beides im Composition Root. Der Preis ist eine
Zeile dort, der Gewinn ist eine Schicht, die von Berichten, Charts und
Antwortschemata nichts weiss.

**Noch kein Upload.** Bis der Proof of Concept einen Anbieter bestaetigt hat
(ADR 0060, Entscheidung Punkt 10), endet der Weg im Verzeichnis. Das ist
kein Platzhalter, sondern der Stand der Entscheidung: Es gibt kein Konto,
kein Token und keine Adresse, und ohne die drei waere jeder Uploadcode eine
Vermutung.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ai_trading_analyst.domain.scheduling import DashboardPublisherError
from ai_trading_analyst.observability.logging_setup import get_logger

from .crypto import (
    KryptoKonfigurationError,
    Verschluesselung,
    kopf,
    leite_schluessel_ab,
)
from .writer import Exportzustand, Schreibbericht, Verzeichnisschreiber

_logger = get_logger(__name__)

SALT_LAENGE = 32
MANIFEST_PFAD = "data/manifest.json"
FORMAT_VERSION = 1
"""Beide muessen mit ``presentation.export`` uebereinstimmen.

Der Klartextkopf nennt den (in Stufe 2 opaken) Namen des Manifests, damit
der Browser weiss, womit er anfangen soll. Dafuer braucht diese Schicht den
kanonischen Pfad und die Formatversion -- und darf beides nicht aus der
Praesentationsschicht holen. Ein Test haelt die Seiten zusammen.
"""


@dataclass(frozen=True, slots=True)
class Exportziel:
    """Wohin der Datenbaum geschrieben wird und wie er geschuetzt ist."""

    wurzel: Path
    zustandsdatei: Path
    passphrase: str | None
    """``None`` heisst Stufe 1: Klartext hinter der Anmeldung an der Kante."""
    iterationen: int


class SnapshotPublisher:
    """Setzt ``DashboardPublisher`` um."""

    def __init__(
        self,
        *,
        snapshot: Callable[[], Iterable[tuple[str, bytes]]],
        ziel: Exportziel,
    ) -> None:
        self._snapshot = snapshot
        self._ziel = ziel

    def publish(self) -> None:
        """Setzt den Port ``DashboardPublisher`` um.

        Ohne Rueckgabewert: Der Tageslauf hat mit dem Bericht nichts vor --
        er steht im Protokoll, und der Lauf haengt nicht davon ab. Wer ihn
        braucht (die Kommandozeile), ruft ``schreibe_baum`` auf.
        """
        self.schreibe_baum()

    def schreibe_baum(self, *, voll: bool = False) -> Schreibbericht:
        """Schreibt den Snapshot.

        ``voll`` verwirft den bekannten Stand und schreibt jede Datei neu.
        Das ist der Weg nach einem Anbieterwechsel und nach jedem Zweifel,
        ob draussen wirklich steht, was hier liegt -- der Zustand behauptet
        etwas ueber ein Verzeichnis, das er nicht selbst kontrolliert.

        Raises:
            DashboardPublisherError: wenn der Baum nicht geschrieben werden
                konnte. Der Aufrufer im Tageslauf isoliert das; das Ergebnis
                des Laufs steht zu diesem Zeitpunkt bereits in der Datenbank.
        """
        try:
            zustand = self._zustand()
            if voll:
                zustand.dateien.clear()
            schreiber = self._schreiber(zustand)
            bericht = schreiber.schreibe(self._snapshot(), zustand)
            zustand.speichere(self._ziel.zustandsdatei)
            return bericht
        except KryptoKonfigurationError as fehler:
            raise DashboardPublisherError(
                f"Verschluesselung nicht einsatzbereit: {fehler}"
            ) from fehler
        except OSError as fehler:
            raise DashboardPublisherError(f"Datenbaum nicht schreibbar: {fehler}") from fehler

    def _zustand(self) -> Exportzustand:
        """Der letzte Stand -- oder ein frischer Baum.

        Salt und Baumkennung entstehen genau einmal und bleiben danach
        stehen. Wuerden sie je Lauf neu gezogen, aenderte sich der abgeleitete
        Schluessel und mit ihm jeder opake Dateiname: Jeder Lauf ergaebe einen
        vollstaendig neuen Baum, und "nur Neues hochladen" gaebe es nicht.
        """
        bekannt = Exportzustand.lade(self._ziel.zustandsdatei)
        if bekannt is not None:
            bekannt.iterationen = self._ziel.iterationen
            return bekannt
        _logger.info("Kein Exportzustand gefunden -- der Datenbaum entsteht neu.")
        return Exportzustand(
            baum_id=str(uuid4()),
            salt=os.urandom(SALT_LAENGE),
            iterationen=self._ziel.iterationen,
        )

    def _schreiber(self, zustand: Exportzustand) -> Verzeichnisschreiber:
        if self._ziel.passphrase is None:
            # Stufe 1. Kein stiller Ersatz: Wer ohne Passphrase exportiert,
            # legt Klartext ab, und das gehoert ins Protokoll.
            _logger.warning(
                "Datenbaum wird im Klartext geschrieben (Stufe 1) -- ohne Passphrase "
                "sieht der Anbieter Berichte, Kurse und Symbole."
            )
            return Verzeichnisschreiber(self._ziel.wurzel)

        schluessel = leite_schluessel_ab(
            self._ziel.passphrase, zustand.salt, zustand.iterationen
        )
        verschluesselung = Verschluesselung(
            schluessel, baum_id=zustand.baum_id, format_version=FORMAT_VERSION
        )
        return Verzeichnisschreiber(
            self._ziel.wurzel,
            verschluesselung=verschluesselung,
            kopf=kopf(
                salt=zustand.salt,
                iterationen=zustand.iterationen,
                format_version=FORMAT_VERSION,
                baum_id=zustand.baum_id,
                manifest=verschluesselung.dateiname(MANIFEST_PFAD),
            ),
        )
