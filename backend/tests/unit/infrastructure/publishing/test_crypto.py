"""Die Serverhaelfte der Zero-Knowledge-Verschluesselung (ADR 0060, Stufe 2).

Kryptocode wird nicht dadurch richtig, dass er laeuft. Diese Tests pruefen
deshalb nicht nur den Hin- und Rueckweg, sondern jede Zusage, die der
Spike-Bericht der Verschluesselung abverlangt: dass eine vertauschte Datei
scheitert, dass ein veraendertes Byte scheitert, dass die Groesse nichts mehr
verraet und dass die Mindestrundenzahl nicht zu unterschreiten ist.
"""

from __future__ import annotations

import gzip
import json

import pytest

from ai_trading_analyst.infrastructure.publishing.crypto import (
    MINDEST_ITERATIONEN,
    KryptoKonfigurationError,
    Verschluesselung,
    entpacke,
    groessenklasse,
    kopf,
    leite_schluessel_ab,
    packe,
)

SALT = b"0123456789abcdef0123456789abcdef"
PASSPHRASE = "korrekt-pferd-batterie-heftklammer-1234"


def verschluesselung(baum_id: str = "baum-1") -> Verschluesselung:
    # Absichtlich die Mindestrundenzahl: Der Test soll messen, was der
    # Betrieb tut, und nicht eine schnellere Sonderfassung.
    schluessel = leite_schluessel_ab(PASSPHRASE, SALT, MINDEST_ITERATIONEN)
    return Verschluesselung(schluessel, baum_id=baum_id, format_version=1)


class TestSchluesselableitung:
    def test_gleiche_eingaben_ergeben_gleiche_schluessel(self) -> None:
        erst = leite_schluessel_ab(PASSPHRASE, SALT, MINDEST_ITERATIONEN)
        zweit = leite_schluessel_ab(PASSPHRASE, SALT, MINDEST_ITERATIONEN)
        assert erst == zweit

    def test_inhalt_und_namen_sind_verschiedene_schluessel(self) -> None:
        """Sonst waere ein bekannter Dateiname ein Orakel gegen den Inhalt."""
        schluessel = leite_schluessel_ab(PASSPHRASE, SALT, MINDEST_ITERATIONEN)
        assert schluessel.inhalt != schluessel.namen
        assert len(schluessel.inhalt) == 32
        assert len(schluessel.namen) == 32

    def test_andere_passphrase_ergibt_anderen_schluessel(self) -> None:
        andere = leite_schluessel_ab(PASSPHRASE + "x", SALT, MINDEST_ITERATIONEN)
        assert andere != leite_schluessel_ab(PASSPHRASE, SALT, MINDEST_ITERATIONEN)

    def test_anderes_salt_ergibt_anderen_schluessel(self) -> None:
        andere = leite_schluessel_ab(PASSPHRASE, b"f" * 32, MINDEST_ITERATIONEN)
        assert andere != leite_schluessel_ab(PASSPHRASE, SALT, MINDEST_ITERATIONEN)

    def test_zu_wenige_runden_werden_abgelehnt(self) -> None:
        """Die Untergrenze ist eine Zusage und kein Vorschlag."""
        with pytest.raises(KryptoKonfigurationError, match="Iterationen"):
            leite_schluessel_ab(PASSPHRASE, SALT, MINDEST_ITERATIONEN - 1)

    def test_zu_kurzes_salt_wird_abgelehnt(self) -> None:
        with pytest.raises(KryptoKonfigurationError, match="Salt"):
            leite_schluessel_ab(PASSPHRASE, b"kurz", MINDEST_ITERATIONEN)

    def test_leere_passphrase_wird_abgelehnt(self) -> None:
        """Kein stiller Rueckfall: Ohne Passphrase gibt es keinen Schluessel."""
        with pytest.raises(KryptoKonfigurationError, match="Passphrase"):
            leite_schluessel_ab("", SALT, MINDEST_ITERATIONEN)


class TestHinUndRueckweg:
    def test_klartext_kommt_unveraendert_zurueck(self) -> None:
        krypto = verschluesselung()
        klartext = json.dumps({"symbol": "AAPL", "kerzen": list(range(50))}).encode()
        chiffrat = krypto.verschluessele("data/stocks/AAPL/chart.json", klartext)
        assert krypto.entschluessele("data/stocks/AAPL/chart.json", chiffrat) == klartext

    def test_leerer_inhalt_geht_auch(self) -> None:
        krypto = verschluesselung()
        chiffrat = krypto.verschluessele("data/leer.json", b"")
        assert krypto.entschluessele("data/leer.json", chiffrat) == b""

    def test_zwei_durchgaenge_ergeben_verschiedene_chiffrate(self) -> None:
        """Zufaellige Nonce je Schreibvorgang.

        Deterministisches Chiffrat verriete dem Anbieter, dass sich eine
        Datei zwischen zwei Exporten nicht geaendert hat -- und ueber die
        Zeit, an welchen Tagen eine Aktie neu bewertet wurde.
        """
        krypto = verschluesselung()
        erst = krypto.verschluessele("data/x.json", b"gleich")
        zweit = krypto.verschluessele("data/x.json", b"gleich")
        assert erst != zweit
        assert krypto.entschluessele("data/x.json", zweit) == b"gleich"


class TestVertauschenUndVeraendern:
    def test_datei_unter_fremdem_pfad_laesst_sich_nicht_lesen(self) -> None:
        """Der Pfad steht in den Zusatzdaten (Negativtest N-Vertauschung).

        Ohne diese Bindung koennte jemand mit Schreibzugriff beim Anbieter
        den Chart einer Aktie unter dem Namen einer anderen ablegen -- und
        die Oberflaeche zeigte ihn arglos an.
        """
        krypto = verschluesselung()
        chiffrat = krypto.verschluessele("data/stocks/AAPL/chart.json", b"inhalt")
        with pytest.raises(Exception):  # noqa: B017 -- InvalidTag der Bibliothek
            krypto.entschluessele("data/stocks/MSFT/chart.json", chiffrat)

    def test_ein_veraendertes_byte_faellt_auf(self) -> None:
        krypto = verschluesselung()
        chiffrat = bytearray(krypto.verschluessele("data/x.json", b"inhalt"))
        chiffrat[-1] ^= 0x01
        with pytest.raises(Exception):  # noqa: B017
            krypto.entschluessele("data/x.json", bytes(chiffrat))

    def test_datei_aus_fremdem_baum_laesst_sich_nicht_lesen(self) -> None:
        """Die Baumkennung bindet die Datei an diesen Datenbaum.

        Das ist der Ersatz fuer die Export-Kennung aus dem Spike-Bericht:
        Sie haette denselben Schutz geleistet, aber jeden Lauf zu einem
        vollstaendigen Upload gemacht.
        """
        chiffrat = verschluesselung("baum-1").verschluessele("data/x.json", b"inhalt")
        with pytest.raises(Exception):  # noqa: B017
            verschluesselung("baum-2").entschluessele("data/x.json", chiffrat)


class TestOpakeNamen:
    def test_name_verraet_den_pfad_nicht(self) -> None:
        krypto = verschluesselung()
        name = krypto.dateiname("data/stocks/AAPL/chart.json")
        assert "AAPL" not in name
        assert "chart" not in name
        assert len(name) == 32

    def test_name_ist_stabil(self) -> None:
        """Sonst waere jede Datei bei jedem Lauf neu hochzuladen."""
        assert verschluesselung().dateiname("data/x.json") == verschluesselung().dateiname(
            "data/x.json"
        )

    def test_verschiedene_pfade_ergeben_verschiedene_namen(self) -> None:
        krypto = verschluesselung()
        assert krypto.dateiname("data/a.json") != krypto.dateiname("data/b.json")

    def test_anderer_baum_ergibt_andere_namen(self) -> None:
        """Nach einem Passphrase-Wechsel ist der ganze Baum ein anderer.

        Gewollt: Die alten Dateien gelten danach als verwaist und werden
        entfernt, statt als lesbare Reste liegen zu bleiben.
        """
        andere = leite_schluessel_ab(PASSPHRASE + "neu", SALT, MINDEST_ITERATIONEN)
        krypto_neu = Verschluesselung(andere, baum_id="baum-1", format_version=1)
        assert krypto_neu.dateiname("data/x.json") != verschluesselung().dateiname("data/x.json")


class TestGroesse:
    @pytest.mark.parametrize(
        ("laenge", "erwartet"),
        [(0, 1024), (1, 1024), (1024, 1024), (1025, 2048), (5000, 8192)],
    )
    def test_groessenklassen(self, laenge: int, erwartet: int) -> None:
        assert groessenklasse(laenge) == erwartet

    def test_zwei_verschieden_grosse_dateien_koennen_gleich_gross_werden(self) -> None:
        """Der Sinn der Auffuellung: Die Groesse soll nichts mehr verraten."""
        krypto = verschluesselung()
        klein = krypto.verschluessele("data/a.json", b"x")
        etwas_groesser = krypto.verschluessele("data/b.json", b"x" * 100)
        assert len(klein) == len(etwas_groesser)

    def test_komprimiert_wird_vor_dem_verschluesseln(self) -> None:
        """Sonst waere das Chiffrat so gross wie der Klartext -- und mehr.

        Eine Kursreihe mit viel Wiederholung muss deutlich kleiner werden;
        nach dem Verschluesseln ginge das nicht mehr.
        """
        krypto = verschluesselung()
        gut_komprimierbar = b'{"c":1.0}' * 5000
        chiffrat = krypto.verschluessele("data/x.json", gut_komprimierbar)
        assert len(chiffrat) < len(gut_komprimierbar) // 4


class TestKlartextkopf:
    def test_kopf_nennt_verfahren_runden_und_salt(self) -> None:
        inhalt = json.loads(
            kopf(
                salt=SALT,
                iterationen=MINDEST_ITERATIONEN,
                format_version=1,
                baum_id="baum-1",
                manifest="abc123",
            )
        )
        assert inhalt["kdf"] == "PBKDF2-HMAC-SHA256"
        assert inhalt["cipher"] == "AES-256-GCM"
        assert inhalt["iterations"] == MINDEST_ITERATIONEN
        assert bytes.fromhex(inhalt["salt"]) == SALT
        assert inhalt["manifest"] == "abc123"

    def test_kopf_enthaelt_keinen_schalter_fuer_das_verfahren(self) -> None:
        """Die schaerfste Zusage dieses Moduls (Bedrohung T21).

        Waere hier ein Feld wie ``encrypted: true``, koennte wer den Kopf
        schreiben darf es auf ``false`` setzen -- und eine Oberflaeche, die
        darauf hoert, naehme danach Klartext an. Das Verfahren ist deshalb
        Eigenschaft des Builds und steht nirgends als Schalter.
        """
        felder = set(
            json.loads(
                kopf(
                    salt=SALT,
                    iterationen=MINDEST_ITERATIONEN,
                    format_version=1,
                    baum_id="baum-1",
                    manifest="abc123",
                )
            )
        )
        assert felder == {"format", "kdf", "iterations", "salt", "cipher", "tree_id", "manifest"}
        assert not {f for f in felder if "encrypt" in f or "plain" in f or "mode" in f}


class TestFormat:
    def test_der_inhalt_ist_gzip_und_laesst_sich_im_browser_entpacken(self) -> None:
        """``DecompressionStream('gzip')`` erwartet genau diesen Rahmen.

        Der Test greift bewusst in das entschluesselte Zwischenergebnis: Ohne
        ihn faende ein Wechsel des Kompressionsverfahrens erst im Browser
        statt -- und dort ohne verwertbare Fehlermeldung.
        """
        klartext = b'{"a":1}'
        roh = packe(klartext)
        laenge = int.from_bytes(roh[:4], "big")
        assert roh[4:6] == b"\x1f\x8b", "Kein gzip-Rahmen -- der Browser kann das nicht lesen"
        assert gzip.decompress(roh[4 : 4 + laenge]) == klartext
        assert entpacke(roh) == klartext

    def test_gleicher_inhalt_ergibt_gleiche_bytes(self) -> None:
        """Ohne ``mtime=0`` stuende in jeder Datei der Zeitpunkt des Packens."""
        assert packe(b"gleich") == packe(b"gleich")
