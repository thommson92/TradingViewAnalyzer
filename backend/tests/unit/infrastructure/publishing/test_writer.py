"""Der Datenbaum als Verzeichnis -- und was er zwischen zwei Exporten tut.

Die interessante Zusage dieses Moduls ist nicht, dass es Dateien schreibt,
sondern **welche es nicht schreibt**: Was sich am Klartext nicht geaendert
hat, bleibt liegen. Ohne diese Eigenschaft laedt jeder Lauf den ganzen Baum
hoch, und in Stufe 2 waere sie auch nicht durch Zufall zu haben -- Chiffrat
sieht mit jeder Nonce anders aus.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from ai_trading_analyst.infrastructure.publishing.crypto import (
    MINDEST_ITERATIONEN,
    Verschluesselung,
    kopf,
    leite_schluessel_ab,
)
from ai_trading_analyst.infrastructure.publishing.writer import (
    Exportzustand,
    Verzeichnisschreiber,
)

SALT = b"0123456789abcdef0123456789abcdef"


def frischer_zustand() -> Exportzustand:
    return Exportzustand(baum_id="baum-1", salt=SALT, iterationen=MINDEST_ITERATIONEN)


def krypto(baum_id: str = "baum-1", passphrase: str = "eine-lange-passphrase") -> Verschluesselung:
    return Verschluesselung(
        leite_schluessel_ab(passphrase, SALT, MINDEST_ITERATIONEN),
        baum_id=baum_id,
        format_version=1,
    )


def dateien(*paare: tuple[str, bytes]) -> Iterable[tuple[str, bytes]]:
    return list(paare)


class TestKlartext:
    def test_schreibt_unter_dem_kanonischen_pfad(self, tmp_path: Path) -> None:
        schreiber = Verzeichnisschreiber(tmp_path)
        bericht = schreiber.schreibe(
            dateien(("data/manifest.json", b"{}"), ("data/stocks/AAPL/chart.json", b"[]")),
            frischer_zustand(),
        )
        assert (tmp_path / "data" / "manifest.json").read_bytes() == b"{}"
        assert (tmp_path / "data" / "stocks" / "AAPL" / "chart.json").read_bytes() == b"[]"
        assert bericht.geschrieben == 2
        assert bericht.unveraendert == 0

    def test_unveraenderte_datei_wird_nicht_neu_geschrieben(self, tmp_path: Path) -> None:
        zustand = frischer_zustand()
        schreiber = Verzeichnisschreiber(tmp_path)
        schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)
        ziel = tmp_path / "data" / "a.json"
        vorher = ziel.stat().st_mtime_ns

        bericht = schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)

        assert bericht.unveraendert == 1
        assert bericht.geschrieben == 0
        assert ziel.stat().st_mtime_ns == vorher

    def test_geaenderte_datei_wird_neu_geschrieben(self, tmp_path: Path) -> None:
        zustand = frischer_zustand()
        schreiber = Verzeichnisschreiber(tmp_path)
        schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)
        bericht = schreiber.schreibe(dateien(("data/a.json", b"zwei")), zustand)
        assert bericht.geschrieben == 1
        assert (tmp_path / "data" / "a.json").read_bytes() == b"zwei"

    def test_datei_wird_neu_geschrieben_wenn_sie_draussen_fehlt(self, tmp_path: Path) -> None:
        """Der Zustand behauptet etwas ueber ein Verzeichnis, das er nicht besitzt.

        Wer die Datei von Hand loescht, soll sie beim naechsten Lauf
        zurueckbekommen -- und nicht ein "unveraendert" fuer etwas, das gar
        nicht mehr da ist.
        """
        zustand = frischer_zustand()
        schreiber = Verzeichnisschreiber(tmp_path)
        schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)
        (tmp_path / "data" / "a.json").unlink()

        bericht = schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)

        assert bericht.geschrieben == 1
        assert (tmp_path / "data" / "a.json").is_file()


class TestVerwaisteDateien:
    def test_was_nicht_mehr_zum_snapshot_gehoert_verschwindet(self, tmp_path: Path) -> None:
        """Sonst waere schon das Serververzeichnis die Datenhalde aus T20."""
        zustand = frischer_zustand()
        schreiber = Verzeichnisschreiber(tmp_path)
        schreiber.schreibe(
            dateien(("data/a.json", b"eins"), ("data/stocks/ALT/chart.json", b"[]")), zustand
        )

        bericht = schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)

        assert bericht.entfernt == 1
        assert not (tmp_path / "data" / "stocks" / "ALT" / "chart.json").exists()
        assert not (tmp_path / "data" / "stocks" / "ALT").exists()
        assert (tmp_path / "data" / "a.json").is_file()

    def test_fremde_dateien_ausserhalb_von_data_bleiben(self, tmp_path: Path) -> None:
        """Neben dem Datenbaum liegt die gebaute Oberflaeche -- sie gehoert
        nicht diesem Modul, und es raeumt sie nicht weg."""
        (tmp_path / "index.html").write_text("<html>", encoding="utf-8")
        Verzeichnisschreiber(tmp_path).schreibe(
            dateien(("data/a.json", b"eins")), frischer_zustand()
        )
        assert (tmp_path / "index.html").is_file()


class TestVerschluesselt:
    def test_dateinamen_sind_opak_und_der_inhalt_ist_chiffrat(self, tmp_path: Path) -> None:
        verschluesselung = krypto()
        schreiber = Verzeichnisschreiber(
            tmp_path,
            verschluesselung=verschluesselung,
            kopf=kopf(
                salt=SALT,
                iterationen=MINDEST_ITERATIONEN,
                format_version=1,
                baum_id="baum-1",
                manifest=verschluesselung.dateiname("data/manifest.json"),
            ),
        )
        schreiber.schreibe(
            dateien(("data/stocks/AAPL/chart.json", b'{"symbol":"AAPL"}')), frischer_zustand()
        )

        assert not (tmp_path / "data" / "stocks").exists()
        geschrieben = [p for p in (tmp_path / "data").iterdir() if p.name != "manifest.head.json"]
        assert len(geschrieben) == 1
        assert "AAPL" not in geschrieben[0].name
        assert b"AAPL" not in geschrieben[0].read_bytes()
        assert (
            verschluesselung.entschluessele(
                "data/stocks/AAPL/chart.json", geschrieben[0].read_bytes()
            )
            == b'{"symbol":"AAPL"}'
        )

    def test_klartextkopf_wird_geschrieben_und_bleibt_stehen(self, tmp_path: Path) -> None:
        verschluesselung = krypto()
        schreiber = Verzeichnisschreiber(
            tmp_path,
            verschluesselung=verschluesselung,
            kopf=kopf(
                salt=SALT,
                iterationen=MINDEST_ITERATIONEN,
                format_version=1,
                baum_id="baum-1",
                manifest="abc",
            ),
        )
        zustand = frischer_zustand()
        schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)
        bericht = schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)

        kopfdatei = tmp_path / "data" / "manifest.head.json"
        assert json.loads(kopfdatei.read_text(encoding="utf-8"))["iterations"] == (
            MINDEST_ITERATIONEN
        )
        # Der Kopf stammt nicht aus dem Snapshot und darf trotzdem nicht als
        # verwaist gelten.
        assert bericht.entfernt == 0
        assert kopfdatei.is_file()

    def test_unveraenderter_klartext_wird_nicht_neu_verschluesselt(self, tmp_path: Path) -> None:
        """Der Kern der Sache: Ohne Vergleich am Klartext saehe jede Datei
        bei jedem Lauf neu aus, weil die Nonce sich aendert."""
        verschluesselung = krypto()
        schreiber = Verzeichnisschreiber(
            tmp_path,
            verschluesselung=verschluesselung,
            kopf=kopf(
                salt=SALT,
                iterationen=MINDEST_ITERATIONEN,
                format_version=1,
                baum_id="baum-1",
                manifest="abc",
            ),
        )
        zustand = frischer_zustand()
        schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)
        ziel = tmp_path / "data" / verschluesselung.dateiname("data/a.json")
        vorher = ziel.read_bytes()

        bericht = schreiber.schreibe(dateien(("data/a.json", b"eins")), zustand)

        assert bericht.unveraendert == 1
        assert ziel.read_bytes() == vorher


class TestZustand:
    def test_hin_und_rueckweg(self, tmp_path: Path) -> None:
        zustand = frischer_zustand()
        Verzeichnisschreiber(tmp_path).schreibe(dateien(("data/a.json", b"eins")), zustand)
        datei = tmp_path.parent / "zustand.json"
        zustand.speichere(datei)

        geladen = Exportzustand.lade(datei)

        assert geladen is not None
        assert geladen.baum_id == zustand.baum_id
        assert geladen.salt == zustand.salt
        assert geladen.dateien == zustand.dateien

    def test_fehlender_zustand_ist_kein_fehler(self, tmp_path: Path) -> None:
        assert Exportzustand.lade(tmp_path / "gibtsnicht.json") is None

    def test_unlesbarer_zustand_kostet_die_ersparnis_nicht_den_export(
        self, tmp_path: Path
    ) -> None:
        datei = tmp_path / "kaputt.json"
        datei.write_text("{kein json", encoding="utf-8")
        assert Exportzustand.lade(datei) is None

    def test_zustand_liegt_nicht_im_datenbaum(self, tmp_path: Path) -> None:
        """Er enthaelt die Zuordnung Pfad -> opaker Name.

        Laege er im veroeffentlichten Verzeichnis, waere die ganze
        Verschluesselung der Dateinamen umsonst.
        """
        zustand = frischer_zustand()
        Verzeichnisschreiber(tmp_path / "public").schreibe(
            dateien(("data/a.json", b"eins")), zustand
        )
        zustandsdatei = tmp_path / "public.zustand.json"
        zustand.speichere(zustandsdatei)
        assert zustandsdatei.is_file()
        assert not (tmp_path / "public" / "public.zustand.json").exists()
