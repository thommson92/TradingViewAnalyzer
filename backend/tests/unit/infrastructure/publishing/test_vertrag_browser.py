"""Der Vertrag zwischen Server- und Browserhaelfte (ADR 0060, Stufe 2).

Die Verschluesselung hat zwei Haelften in zwei Sprachen: Python mit
``cryptography`` auf dem Server, WebCrypto im Browser. Beide muessen
dasselbe Format meinen -- und ob sie das tun, faellt sonst erst auf, wenn
jemand vor einem Dashboard steht, das nichts anzeigt und keine verwertbare
Meldung gibt.

Deshalb liegt eine feste Datei im Repository, die **beide** Seiten
entschluesseln: dieser Test und ``frontend/src/lib/datenbaum.test.ts``.
Schlaegt einer von beiden fehl, sind die Haelften auseinandergelaufen.

**Neu erzeugt wird die Datei nur absichtlich.** Byte fuer Byte reproduzieren
laesst sie sich nicht -- die Nonce ist zufaellig, und das soll sie sein.
Wer das Format aendert, erzeugt sie mit dem Skript unten neu und bringt
danach **beide** Tests wieder auf gruen; ein einseitig angepasster Vertrag
ist keiner. In der Datei stehen ausdruecklich keine echten Daten und keine
echte Passphrase.

.. code-block:: python

    # cd backend && PYTHONPATH=src .venv/bin/python
    import json, hashlib
    from pathlib import Path
    from ai_trading_analyst.infrastructure.publishing.crypto import (
        MINDEST_ITERATIONEN, Verschluesselung, leite_schluessel_ab,
    )

    alt = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    salt = bytes.fromhex(alt["salt"])
    klartext = alt["klartext"].encode("utf-8")
    krypto = Verschluesselung(
        leite_schluessel_ab(alt["passphrase"], salt, MINDEST_ITERATIONEN),
        baum_id=alt["tree_id"],
        format_version=1,
    )
    alt["chiffrat"] = krypto.verschluessele(alt["pfad"], klartext).hex()
    alt["dateiname"] = krypto.dateiname(alt["pfad"])
    alt["klartext_sha256"] = hashlib.sha256(klartext).hexdigest()
    Path(FIXTURE).write_text(
        json.dumps(alt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_trading_analyst.infrastructure.publishing.crypto import (
    Verschluesselung,
    leite_schluessel_ab,
)

FIXTURE = (
    Path(__file__).resolve().parents[5]
    / "frontend"
    / "src"
    / "lib"
    / "__fixtures__"
    / "zero-knowledge.json"
)


def fixture() -> dict[str, str | int]:
    daten: dict[str, str | int] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return daten


class TestVertrag:
    def test_die_fixture_liegt_da_wo_beide_seiten_sie_finden(self) -> None:
        assert FIXTURE.is_file(), (
            f"{FIXTURE} fehlt -- ohne sie prueft niemand mehr, ob Server und "
            "Browser dasselbe Format meinen."
        )

    def test_die_serverhaelfte_entschluesselt_sie(self) -> None:
        daten = fixture()
        schluessel = leite_schluessel_ab(
            str(daten["passphrase"]),
            bytes.fromhex(str(daten["salt"])),
            int(daten["iterations"]),
        )
        krypto = Verschluesselung(
            schluessel, baum_id=str(daten["tree_id"]), format_version=int(daten["format"])
        )
        klartext = krypto.entschluessele(
            str(daten["pfad"]), bytes.fromhex(str(daten["chiffrat"]))
        )
        assert klartext.decode("utf-8") == daten["klartext"]
        assert hashlib.sha256(klartext).hexdigest() == daten["klartext_sha256"]

    def test_der_opake_dateiname_stimmt_ueberein(self) -> None:
        """Auch die Namensbildung ist Teil des Vertrags: Der Browser leitet
        sie selbst ab, statt eine Zuordnung mitzuschleppen."""
        daten = fixture()
        schluessel = leite_schluessel_ab(
            str(daten["passphrase"]),
            bytes.fromhex(str(daten["salt"])),
            int(daten["iterations"]),
        )
        krypto = Verschluesselung(
            schluessel, baum_id=str(daten["tree_id"]), format_version=int(daten["format"])
        )
        assert krypto.dateiname(str(daten["pfad"])) == daten["dateiname"]

    def test_die_fixture_nennt_verfahren_und_runden(self) -> None:
        """Wer sie liest, soll nicht im Code nachsehen muessen, wogegen er
        prueft."""
        daten = fixture()
        assert daten["kdf"] == "PBKDF2-HMAC-SHA256"
        assert daten["cipher"] == "AES-256-GCM"
