"""Die Verdrahtung des Exportschritts in der Composition Root (ADR 0060).

Hier steht keine Verschluesselung und kein Dateisystem, sondern die Kette
von Entscheidungen davor: Ist der Schritt eingeschaltet? Liegt ein Ziel vor?
Ist die Passphrase da, wenn verschluesselt werden soll? Liegt der
Zustandsvermerk ausserhalb dessen, was hinausgeht?

**Die wichtigste Zusage dieser Datei** ist die dritte: Wer ``encrypt`` sagt
und die Passphrase vergisst, bekommt einen Abbruch und keinen Klartextbaum.
Ein Tippfehler im Namen der Umgebungsvariablen wuerde sonst stillschweigend
Berichte, Kurse und Symbole beim Anbieter ablegen -- das ist die Lage, die
ADR 0049 mit "solange nichts das eigene Netz verlaesst" bewusst vermieden
hat.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ai_trading_analyst.bootstrap import build_dashboard_publisher
from ai_trading_analyst.config.loader import load_config
from ai_trading_analyst.config.settings import (
    AppConfig,
    DashboardExportConfig,
    MissingSecretError,
    Secrets,
)
from ai_trading_analyst.domain.analysis import UnitOfWork
from ai_trading_analyst.infrastructure.publishing import MINDEST_ITERATIONEN


def uow_factory() -> Callable[[], UnitOfWork]:
    def fabrik() -> UnitOfWork:  # pragma: no cover -- wird hier nie gerufen
        raise AssertionError("Die Verdrahtung darf keine Datenbank oeffnen.")

    return fabrik


def konfiguration(**felder: object) -> AppConfig:
    basis = load_config().config
    return basis.model_copy(update={"dashboard_export": DashboardExportConfig(**felder)})


def baue(config: AppConfig, secrets: Secrets, root: Path) -> object:
    return build_dashboard_publisher(config, secrets, root, uow_factory=uow_factory())


class TestAbgeschaltet:
    def test_ausgeliefert_entsteht_kein_exportschritt(self, tmp_path: Path) -> None:
        """Ein frisch aufgesetzter Server exportiert nichts."""
        assert baue(konfiguration(), Secrets(), tmp_path) is None

    def test_ohne_verzeichnis_bricht_es_ab(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="directory"):
            baue(konfiguration(target="directory"), Secrets(), tmp_path)


class TestKeinRueckfallAufKlartext:
    def test_ohne_passphrase_bricht_der_verschluesselte_export_ab(self, tmp_path: Path) -> None:
        """Kein stiller Rueckfall -- der Kern der Stufe-2-Zusage."""
        with pytest.raises(MissingSecretError, match="ATA_DASHBOARD_EXPORT_PASSPHRASE"):
            baue(
                konfiguration(target="directory", directory="var/dashboard"),
                Secrets(),
                tmp_path,
            )

    def test_mit_passphrase_entsteht_er(self, tmp_path: Path) -> None:
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        assert (
            baue(
                konfiguration(target="directory", directory="var/dashboard"),
                secrets,
                tmp_path,
            )
            is not None
        )

    def test_ohne_verschluesselung_braucht_es_keine_passphrase(self, tmp_path: Path) -> None:
        """Stufe 1 ist erlaubt -- sie muss nur ausdruecklich gewaehlt sein."""
        assert (
            baue(
                konfiguration(target="directory", directory="var/dashboard", encrypt=False),
                Secrets(),
                tmp_path,
            )
            is not None
        )


class TestFruehePruefungen:
    """Alles, was hier abbricht, bricht **vor** dem halbstuendigen Backfill ab."""

    def test_zu_wenige_runden_brechen_frueh_ab(self, tmp_path: Path) -> None:
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        with pytest.raises(ValueError, match=str(MINDEST_ITERATIONEN)):
            baue(
                konfiguration(
                    target="directory", directory="var/dashboard", pbkdf2_iterations=1000
                ),
                secrets,
                tmp_path,
            )

    def test_zustandsdatei_im_datenbaum_wird_abgelehnt(self, tmp_path: Path) -> None:
        """Sie traegt die Zuordnung von Pfad zu opakem Namen.

        Laege sie im veroeffentlichten Verzeichnis, ginge sie beim naechsten
        Upload mit hinaus -- und die Verschluesselung der Dateinamen waere
        umsonst gewesen.
        """
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        with pytest.raises(ValueError, match="veroeffentlichten Verzeichnis"):
            baue(
                konfiguration(
                    target="directory",
                    directory="var/dashboard",
                    state_file="var/dashboard/zustand.json",
                ),
                secrets,
                tmp_path,
            )

    def test_der_standardort_liegt_neben_dem_baum(self, tmp_path: Path) -> None:
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        veroeffentlicher = baue(
            konfiguration(target="directory", directory="var/dashboard"), secrets, tmp_path
        )
        assert veroeffentlicher is not None
        ziel = veroeffentlicher._ziel  # type: ignore[attr-defined]
        assert not ziel.zustandsdatei.is_relative_to(ziel.wurzel)


class TestGeheimnisse:
    def test_die_passphrase_wird_zur_schwaerzung_angemeldet(self) -> None:
        """ADR 0044: Was in ``Secrets`` steht, darf nicht ins Protokoll.

        Der Exportschritt protokolliert Ziel, Umfang und Dauer -- und im
        Fehlerfall die Meldung der Bibliothek. Eine Passphrase, die dabei
        durchschluepft, stuende in einer Datei auf dem Handelsrechner.
        """
        from ai_trading_analyst.observability.secret_redaction import redact_registered

        Secrets(dashboard_export_passphrase="streng-geheime-passphrase")

        assert "streng-geheime-passphrase" not in redact_registered(
            "Fehler mit streng-geheime-passphrase im Text"
        )


class TestKommandozeile:
    def test_publish_meldet_den_abgeschalteten_export_ohne_datenbank(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Rueckgabewert 2 und eine Meldung -- **vor** dem Verbindungsversuch.

        Ausgeliefert steht der Export auf ``none``. Ein Aufruf soll das sagen
        und nicht hinter einem Datenbankfehler verschwinden, der mit der Sache
        nichts zu tun hat.
        """
        from ai_trading_analyst import cli

        code = cli.main(["publish"])

        assert code == 2
        assert "abgeschaltet" in capsys.readouterr().err
