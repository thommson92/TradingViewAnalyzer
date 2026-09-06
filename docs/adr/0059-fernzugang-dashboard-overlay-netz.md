# ADR 0059: Fernzugang zum Dashboard über ein identitätsgebundenes Overlay-Netz — keine öffentliche Erreichbarkeit

- Status: Vorgeschlagen
- Datum: 2026-09-06

## Kontext

[ADR 0049](0049-dashboard-mvp-nur-lan.md) hat den externen Zugriff auf das
Dashboard (F12, Doc 10 §19 Frage 13) für das MVP verneint — kein Zugriff
von außen, keine eigene Authentifizierung — und die Neubewertung „nach
stabilem Betrieb" angekündigt, „als eigenes ADR, zusammen mit der
Reverse-Proxy-/Container-Frage aus ADR 0036". Der Tageslauf läuft seit dem
2026-09-01 automatisch (Doc 14, Betriebszustand). Dies ist die
Neubewertung. Ihre Grundlage — Ist-Aufnahme, Threat Model,
Variantenvergleich, PoC-Plan — steht im Spike-Bericht
[docs/requirements/f12-externer-zugriff-spike.md](../requirements/f12-externer-zugriff-spike.md).

Was den Rahmen setzt:

- **Der Server ist der Handelsrechner.** Auf demselben Windows-Server läuft
  die TWS mit angemeldetem Live-Konto, und dieselbe TWS-Instanz überträgt
  für die Trade Automation Toolbox echte Optionsorders; der TWS-weite
  Schalter „Read-Only API" ist deshalb bewusst aus (Doc 14, Stufe D;
  [ADR 0014](0014-ibkr-produktivintegration-freigegeben.md)). Jeder Prozess
  auf diesem Rechner, der `127.0.0.1:7496` erreicht, kann Orders
  übermitteln. Ein Dashboard-Dienst auf diesem Rechner ist damit nicht nur
  ein Leser von Analyseergebnissen, sondern ein möglicher Sprungpunkt.
- **Es gibt genau einen Nutzer** (Doc 01 §5). Finnhubs Einschränkung L8
  ([ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md)) untersagt die
  Weitergabe abgeleiteter Daten an Dritte, das Deployment-Gate aus
  [ADR 0022](0022-research-agent-quellen.md) jede Bereitstellung außerhalb
  des privaten Prototyps. Ein öffentliches oder mehrnutzerfähiges Dashboard
  ist damit gar nicht zu entscheiden — es ist ausgeschlossen.
- **Die API ist lesend** ([ADR 0053](0053-lese-api-kein-lauf-ueber-http.md)).
  Das war die stille Voraussetzung dafür, dass ADR 0049 ohne
  Authentifizierung auskam, und bleibt sie.
- **Das Repository ist öffentlich** ([ADR 0031](0031-merge-schutz-aktiv.md)).
  Pfade, Ports, Endpunkte und Betriebsanleitung sind für jeden lesbar.
  Sicherheit durch Verborgenheit gibt es nicht; Hostnamen, Adressen und
  Kontonamen des Betriebs dürfen in keinem Dokument stehen.
- Doc 14, Stufe J sieht den Dienst mit `--host 0.0.0.0` und einer
  Firewallregel im privaten Profil vor. **Der Dienst läuft auf dem Server
  noch nicht** (Doc 14, Betriebszustand). Diese Entscheidung greift also
  ein, bevor ein Ist-Zustand entsteht, der umgebaut werden müsste.

Untersucht wurden fünf Wege: VPN am Router, VPN-Server auf dem
Windows-Server, ein identitätsgebundenes Overlay-Netz (WireGuard-basiertes
Mesh mit Koordinationsdienst, Anmeldung über einen Identitätsanbieter mit
MFA, Zugriffsregeln je Gerät, nur ausgehende Verbindungen), ein
Identity-Aware Proxy mit ausgehendem Tunnel (Zero Trust Network Access) und
ein Reverse Proxy mit TLS und starker Authentifizierung auf dem Server
hinter einer Portweiterleitung — samt Kombinationen. Die vollständige
Bewertung steht im Spike-Bericht, Abschnitte 6 und 7.

## Entscheidung

1. **Das Dashboard wird nicht öffentlich erreichbar.** Es bekommt keinen
   öffentlichen Hostnamen und keinen eingehenden Port — weder am
   Windows-Server noch am Router. Die Frage „extern erreichbar" wird als
   **privater Fernzugang für die registrierten Geräte des Nutzers**
   beantwortet, nicht als Veröffentlichung im Internet.
2. **Der Fernzugang läuft über ein identitätsgebundenes Overlay-Netz.**
   Der Server verbindet sich ausschließlich ausgehend mit dem
   Koordinationsdienst; jedes Gerät des Nutzers wird über den
   Identitätsanbieter mit **phishing-resistenter MFA** (Passkey oder
   Hardware-Schlüssel, wo der Anbieter es zulässt) registriert und erhält
   einen eigenen, ablaufenden Geräteschlüssel. Eine Zugriffsregel erlaubt
   **nur diesen Geräten** den Port des Dashboards auf dem Server; alles
   Übrige ist verweigert. Ein Gerät, das nicht registriert ist, sieht den
   Dienst nicht — es erreicht nicht einmal einen Anmeldedialog.
3. **Der Dienst bindet nicht mehr an alle Schnittstellen.** Er lauscht
   auf der Loopback- und der Overlay-Schnittstelle; die Firewallregel
   gilt nur für die Overlay-Schnittstelle. Die LAN-Freigabe im privaten
   Profil aus Doc 14, Stufe J, Schritt 4 **entfällt**: Ein Weg statt zwei,
   und ein Tablet im heimischen WLAN nimmt denselben Weg wie das
   Smartphone unterwegs. (Präzisierung zu [ADR 0052](0052-dashboard-als-statischer-export.md),
   Punkt 3 — der dort beschlossene Autostart-Eintrag bleibt, seine
   Bindung ändert sich.)
4. **Der Dienst wird gehärtet, unabhängig vom Weg.** Eigenes lokales
   Dienstkonto ohne Administratorrechte für den Autostart-Eintrag; eigene
   PostgreSQL-Rolle mit ausschließlich Leserechten; `/docs` und
   `/openapi.json` außerhalb der Entwicklung abgeschaltet; Sicherheits-Header
   (`Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`,
   `frame-ancestors`); Zugriffsprotokoll in eine Datei mit Rotation, ohne
   Geheimnisse und ohne Anfrageinhalte; der Dashboard-Prozess erhält nur
   das eine Geheimnis, das er braucht — die Datenbank-URL der Leserolle —
   und nicht die ganze `.env`. Das sind Anwendungsänderungen und ein
   eigenes Feature; sie stehen als Bedingung hier, nicht als Umsetzung.
5. **Die API bleibt lesend, und das Dashboard bekommt in dieser Stufe keine
   eigene Anmeldung.** `ATA_SESSION_SECRET` bleibt reserviert. Die
   Identitätsprüfung sitzt vor dem Dienst, an der Netzgrenze, mit MFA und
   Gerätebindung; eine zweite Anmeldung im Dienst brächte Passwortspeicher
   und Sitzungsverwaltung in eine Anwendung, die dafür heute keinen
   Gegner hat. **Sollten je schreibende Funktionen kommen** — Läufe
   auslösen, Konfiguration ändern, irgendetwas, das eine Order oder ein
   Modell berührt —, ist das ein neues ADR mit eigener Anmeldung im
   Dienst, Step-up-Authentifizierung je Aktion, getrennter Berechtigung
   für Schreibpfade und unveränderbarem Audit-Protokoll. Die Trennung
   zwischen lesender Anzeige und transaktionalen Funktionen ist damit
   festgeschrieben: Es gibt nur die erste.
6. **Der Notausschalter ist Teil der Einrichtung, nicht ein Nachtrag.** Der
   Fernzugang wird an drei Stellen unabhängig voneinander gekappt: Sperren
   oder Löschen des Server-Knotens im Koordinationsdienst (wirkt sofort,
   von jedem Gerät aus), Anhalten des Overlay-Dienstes und des
   Autostart-Eintrags auf dem Server, Löschen der Firewallregel. Die
   Reihenfolge und die Prüfung, dass sie gewirkt haben, stehen in Doc 14.
7. **Erst ein Proof of Concept, dann der Betrieb.** Der PoC läuft ohne
   Produktivdaten und ohne produktive Zugangsdaten: eigene Testinstanz auf
   eigenem Port, eigene Datenbank mit ausschließlich synthetischen Daten
   aus den Fixture-Anbietern, nur Testgeräte in der Zugriffsregel,
   vollständiger Rückbau. Die Abnahmekriterien und Negativtests stehen im
   Spike-Bericht, Abschnitt 11. Der produktive Fernzugang wird als eigenes
   Feature umgesetzt, nachdem der PoC bestanden ist — und erst dann wird
   dieses ADR angenommen.
8. **Was nicht entschieden wird:** kein Container, kein Reverse Proxy
   (Punkt 1 aus ADR 0052 bleibt — es gibt keinen öffentlichen Endpunkt, den
   ein Proxy schützen müsste), kein Link in der Ergebnismeldung
   ([ADR 0040](0040-inhalt-der-ergebnismeldung.md) bleibt unverändert; ob ein
   Overlay-Name, der nur auf registrierten Geräten auflöst, dort hineindarf,
   ist eine eigene Frage), keine Anbieterwahl (sie gehört in den PoC, mit
   Prüfung der Nutzungsbedingungen).

## Begründung

**Die kleinste Angriffsfläche ist die, die es nicht gibt.** Ein
Overlay-Netz mit ausgehender Verbindung öffnet am Handelsrechner keinen
Port und am Router keine Weiterleitung. Unauthentifizierte Pakete erreichen
den Dienst nicht — es gibt keinen Anmeldedialog, den man mit Passwörtern
bombardieren, und keine TLS-Endstelle, die man falsch konfigurieren könnte.
Brute Force und Credential Stuffing zielen auf den Identitätsanbieter, der
dafür gebaut ist, nicht auf einen Python-Prozess neben der TWS. Das ist die
Variante, die alle fünf Vorzugskriterien der Aufgabenstellung erfüllt:
keine eingehenden Ports, Dienst nur an internen Schnittstellen,
vorgelagerte starke Identitätsprüfung mit MFA, Least Privilege je Gerät,
kein allgemein erreichbarer Webserver auf dem Windows-Server.

**Ein Reverse Proxy auf dem Server hinter einer Portweiterleitung ist das
Gegenteil davon.** Er macht den Handelsrechner zu einem im Internet
erreichbaren Webserver — mit eigener TLS-Endstelle, eigenem
Anmeldeverfahren, eigenem Ratenbegrenzer, eigenem Patch-Turnus, alles
selbst zu betreiben, und mit einem Uplink, den jeder Unbekannte mit
Verkehr belegen kann, während der Tageslauf gerade Kerzen holt. Doc 10 §13
nennt diesen Weg nur als Alternative zum privaten Netz oder VPN; der Spike
bestätigt die Reihenfolge.

**Ein Identity-Aware Proxy mit ausgehendem Tunnel ist die zweitbeste Wahl,
nicht die beste.** Er braucht ebenfalls keinen eingehenden Port und stellt
MFA vor den Dienst — aber er gibt dem Dashboard einen öffentlichen
Hostnamen, verlegt die TLS-Endstelle zum Anbieter, der damit den Klartext
der Analyseergebnisse sieht (eine Frage an Finnhubs L8, die der
Overlay-Weg gar nicht erst stellt, weil dort Ende-zu-Ende verschlüsselt
wird), und verlangt, dass der Dienst das Identitätstoken des Anbieters
selbst prüft — sonst schützt nur die Konfiguration des Tunnels. Er bleibt
der Ausweichweg, falls Client-Software auf den Endgeräten nicht in Frage
kommt.

**VPN am Router oder VPN-Server auf dem Windows-Server** öffnen einen
eingehenden Port (UDP) — am Router noch vertretbar, am Handelsrechner
nicht —, kennen meist nur ein geteiltes Geheimnis oder ein Schlüsselpaar
ohne Identitätsanbieter, keine MFA und keine Zugriffsregel je Gerät, und
lassen ein verbundenes Gerät im gesamten Heimnetz stehen statt an einem
Port. Der Overlay-Weg ist dasselbe Prinzip mit Identität, Gerätebindung
und Least Privilege.

**Der Preis des Overlay-Wegs ist eine Abhängigkeit, und sie ist benannt.**
Der Koordinationsdienst ist ein Drittanbieter; sein Agent läuft auf dem
Server als Dienst mit Systemrechten. Dagegen stehen drei Dinge: Der
Datenverkehr ist Ende-zu-Ende verschlüsselt, der Koordinationsdienst sieht
Schlüssel und Metadaten, keine Inhalte; ein Ausfall des Anbieters kostet
den Fernzugang, nicht den Tageslauf — der Dispatcher braucht das Overlay
nicht, und die Telegram-Meldung bleibt; und die Alternative dazu ist nicht
„keine Abhängigkeit", sondern ein selbst betriebener Bastion-Server mit
selbst betriebener Anmeldung — mehr Betrieb, gleiche Vertrauensfrage,
anderer Anbieter. Wer die Abhängigkeit nicht will, kann den
Koordinationsdienst selbst hosten; das ist ein eigener Betriebsaufwand und
wird im PoC nicht verfolgt.

**Warum keine Anmeldung im Dienst, obwohl Doc 10 §13 „Login" verlangt:**
Doc 10 §13 stammt aus der Planung vor der ersten Zeile Code und setzt
stillschweigend ein öffentlich erreichbares Dashboard voraus. Die Anmeldung
mit MFA findet statt — an der Netzgrenze, je Gerät, bevor ein Paket den
Dienst erreicht. Eine zweite Anmeldung im Dienst schützte gegen genau
einen Fall: ein registriertes, entsperrtes Gerät in fremder Hand. Der
Schaden dort ist Lesen. Das Verhältnis rechtfertigt heute keinen
Passwortspeicher in der Anwendung. Diese Abwägung ist umkehrbar und wird
im Spike-Bericht als Entscheidungspunkt geführt; sie kehrt sich sicher um,
sobald es einen Schreibpfad gibt (Punkt 5).

## Konsequenzen

**Positiv**

- Kein Port am Handelsrechner, keine Weiterleitung am Router, kein
  öffentlicher Name. Von außen sieht der Server aus wie heute.
- Der Zugriff ist auf benannte Geräte eines benannten Nutzers beschränkt;
  Finnhub L8 und das Deployment-Gate aus ADR 0022 bleiben gewahrt, weil
  niemand außer dem Nutzer etwas sieht.
- Der Notausschalter wirkt sofort und von unterwegs.
- Die Härtung aus Punkt 4 nützt auch im LAN-Betrieb; sie ist nicht an
  den Fernzugang gebunden.

**Negativ und offen**

- **Client-Software auf jedem Gerät**, das zugreifen soll, und ein Konto
  bei einem Identitätsanbieter mit Passkey. Ein fremder Browser kommt nicht
  heran — das ist gewollt, aber unbequem.
- **Sperre am Identitätsanbieter heißt kein Fernzugang.** Der
  Wiederherstellungsweg (Recovery-Codes, zweiter Schlüssel) gehört
  offline abgelegt, bevor der erste Knoten registriert wird.
- **Ein Dienst mit Systemrechten mehr** auf dem Server (der Overlay-Agent),
  vom Anbieter gepatcht. Automatische Aktualisierung ist einzuschalten; das
  Pflegeprotokoll in Doc 14 wächst um den Agenten und um die
  Ablauffristen der Geräteschlüssel.
- **Der Web-Stack wird erreichbar** — wenn auch nur für eigene Geräte.
  Meldungen aus `audit.yml` zu `uvicorn`, `starlette`, `fastapi` und `h11`
  sind künftig binnen Tagen zu bescheiden, nicht im Quartalsturnus.
- **Loopback lässt sich auf Windows nicht verlässlich per Firewall
  trennen.** Ob das Dienstkonto des Dashboards an `127.0.0.1:7496`
  gehindert werden kann, prüft der PoC; die harte Grenze wäre ein
  eigener Host für das Dashboard. Das ist für die lesende Stufe nicht
  gefordert und bleibt als Ausbaustufe vorgemerkt — Bedingung für jeden
  Schreibpfad.
- **Eine Anwendungsänderung ist Voraussetzung** (Punkt 4): Bindung,
  Header, Abschalten von `/docs`, eigene Umgebung für den
  Dashboard-Prozess, Zugriffsprotokoll in Datei. Ohne sie wird der
  Fernzugang nicht produktiv geschaltet.
- **Dokumentation, die nachzuziehen ist:** Doc 14 Stufe J (Bindung,
  Firewallregel, Dienstkonto, Notfallkarte, neue Stufe für den
  Fernzugang), Doc 10 §13 und §14, Doc 13, Doc 11 (Satz „nur im eigenen
  Netz erreichbar"), README (der Absatz zu `POST /api/v1/analysis-runs`
  ist seit ADR 0053 überholt).

**Was dieses ADR ablöst, sobald es angenommen ist:** die Aussage „keine
Exposition" aus ADR 0049 wird zu „keine öffentliche Exposition; privater
Fernzugang über das Overlay-Netz"; Punkt 3 aus ADR 0052 (Bindung an die
LAN-Schnittstelle, Firewallregel im privaten Profil) wird durch Punkt 3
oben ersetzt. ADR 0049 und ADR 0052 werden nicht rückwirkend geändert.
