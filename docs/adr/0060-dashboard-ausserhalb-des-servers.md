# ADR 0060: Das Dashboard läuft außerhalb des Servers — Snapshot je Lauf, ausgehend hochgeladen, Anmeldung an der Kante, Zero-Knowledge als Zielstufe

- Status: Vorgeschlagen
- Datum: 2026-09-06

## Kontext

[ADR 0049](0049-dashboard-mvp-nur-lan.md) hat den externen Zugriff auf das
Dashboard (F12) für das MVP verneint und die Neubewertung nach stabilem
Betrieb angekündigt. Der Tageslauf läuft seit dem 2026-09-01 automatisch.
Ein erster Spike vom 2026-09-06 hat den **Zugang zum Server** untersucht —
privater Fernzugang über ein identitätsgebundenes Overlay-Netz — und ist
mit ADR 0059 (Vorgeschlagen) auf dem Branch
`feature/spike-dashboard-externer-zugriff` **zurückgestellt**: Der Weg
verlangt Client-Software auf jedem Gerät, und der Inhaber will von
beliebigen Geräten aus zugreifen, mit einer einfachen Anmeldung. Der
Zugriff auf das Dashboard gilt ihm als nicht sicherheitskritisch; der
Server soll durch das Dashboard nicht erreichbar werden.

Dieses ADR beantwortet F12 deshalb umgekehrt: **Nicht der Nutzer kommt zum
Server, die Ergebnisse gehen zum Nutzer.** Grundlage ist der Spike-Bericht
[docs/requirements/f12-externes-hosting-spike.md](../requirements/f12-externes-hosting-spike.md);
die Vorgaben des Inhabers stehen dort in Abschnitt 3.1.

Was den Rahmen setzt:

- **Das Dashboard ist bereits ein statischer Export** ohne Geschäftslogik
  ([ADR 0052](0052-dashboard-als-statischer-export.md)); seine Daten kommen
  aus elf lesenden Endpunkten ([ADR 0053](0053-lese-api-kein-lauf-ueber-http.md)),
  deren Antworten sich als Dateien ablegen lassen. Der Chart-Payload einer
  Aktie über fünf Jahre ist gemessen rund 350 KB roh, der Vollexport aller
  Ansichten rund 75 MB roh und 17 MB komprimiert.
- **Der Server spricht bereits ausgehend mit vier Diensten** (Finnhub,
  EDGAR, Anthropic, Telegram), mit Tokens aus `ATA_`-Variablen und
  Fehlerisolation am Laufende ([ADR 0024](0024-benachrichtigungskanal-telegram.md)).
  Ein Upload nach dem Lauf fügt sich in dieses Muster.
- **Der Server ist der Handelsrechner** (TWS mit Orderrecht) und bleibt
  ohne eingehende Freigabe — das ist die Bedingung, unter der ADR 0049
  ohne Authentifizierung auskam, und sie bleibt hier unberührt.
- **Genau ein Nutzer.** Finnhubs L8 ([ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md))
  und das Deployment-Gate aus [ADR 0022](0022-research-agent-quellen.md)
  stellen sich mit einem Hosting-Anbieter neu: nicht als Frage nach
  fremden Lesern, sondern nach dem Anbieter als Dritten.
- **Das Repository ist öffentlich** ([ADR 0031](0031-merge-schutz-aktiv.md)):
  Hostnamen, Projektnamen und Konten gehören in kein Dokument und keinen
  Workflow.

Untersucht wurden: ein statischer Export bei einem Anbieter mit Anmeldung
an der Kante, ein eigener kleiner Server mit Reverse Proxy, ein
Zero-Knowledge-Export (auf dem Server verschlüsselt, im Browser
entschlüsselt) allein und hinter der Kantenanmeldung, eine gehostete API
mit Datenbankkopie, sowie Datenwege und Bauweisen — Spike-Bericht,
Abschnitte 6 und 7.

## Entscheidung

1. **Der Server bleibt unerreichbar.** Kein eingehender Port, kein Agent,
   kein Tunnel. Die einzige neue Verbindung geht vom Server nach außen:
   ein HTTPS-Upload mit einem Token, das beim Anbieter **auf genau diese
   Seite und auf Schreiben** beschränkt ist.
2. **Nach jedem Lauf verlässt ein Snapshot den Server.** Ein Exportschritt
   am Ende von `RunAnalysisUseCase.execute()` — Port `DashboardPublisher`
   neben `Notifier`, Adapter in der Infrastruktur, **dieselbe
   Fehlerisolation wie die Telegram-Meldung**: Ein fehlgeschlagener Upload
   wird protokolliert und über Telegram gemeldet, der Lauf gilt trotzdem als
   erledigt. Dazu `cli publish` für Handbetrieb und Vollexport. Geschaltet
   wird über ein Argument der Aufgabenplanung; die ausgelieferte
   Konfiguration steht auf `none` ([ADR 0036](0036-nativer-windows-betrieb.md),
   Punkt 4).
3. **Der Snapshot ist ein Datenbaum aus den Antworten der API**, erzeugt
   von denselben Anwendungsfällen und Antwortschemata — keine zweite
   Rechnung, kein zweiter Zuschnitt —, mit einem **Manifest** (Zeitpunkt,
   Lauf-ID, Versionen, Verfahren). Die Oberfläche zeigt den Stand aus dem
   Manifest an jeder Ansicht: Ein alter Stand muss alt aussehen.
4. **Die Oberfläche bekommt einen statischen Datenmodus.** Dasselbe
   Frontend, gebaut mit einer Umgebungsvariablen, holt seine Antworten aus
   dem Datenbaum statt von der API; Paginierung und Filter der Läufe
   geschehen im Browser. Der Server baut diese Fassung wie heute die
   LAN-Fassung (Node als Werkzeug, ADR 0052) und lädt Oberfläche und
   Datenbaum als **ein** Deployment hoch. Das LAN-Dashboard auf dem Server
   bleibt bestehen.
5. **Außerhalb liegt eine statische Seite hinter der Anmeldung des
   Anbieters** (beispielhaft: Cloudflare Pages mit Access, Azure Static
   Web Apps). Die Zugriffsregel deckt den **ganzen Hostnamen** ab —
   jede Datei, auch Vorschau- und Zweigadressen —, erlaubt **genau einen
   Nutzer** und verlangt MFA über ein Identitätsanbieter-Konto mit
   Authenticator-App oder Passkey; ein E-Mail-Einmalcode ist nur Rückfall.
   Sitzung kurz (Vorschlag 24 Stunden), Cookies `Secure`, `HttpOnly`,
   `SameSite`, `noindex`, nichtssagende Namen. Kein eigenes
   Anmeldeformular, kein eigener Sitzungscode; `ATA_SESSION_SECRET` bleibt
   reserviert.
6. **Zero-Knowledge ist die Zielstufe, nicht ein Extra.** In Stufe 2 wird
   der Datenbaum auf dem Server verschlüsselt — Schlüssel aus einer
   Passphrase abgeleitet (PBKDF2-SHA256, hohe Iterationszahl, Salt im
   Manifest), je Datei AES-256-GCM mit zufälliger Nonce und dem
   **Dateipfad als Zusatzdaten**, komprimiert vor dem Verschlüsseln — und
   im Browser mit WebCrypto entschlüsselt. Der Anbieter sieht Chiffrat;
   gefälschte oder vertauschte Datendateien werden verworfen; die
   Passphrase im Passwortmanager ist die „einfache Anmeldung", die
   Kantenanmeldung bleibt als MFA davor. Stufe 1 wird so gebaut, dass
   Stufe 2 eine Schreib- und eine Ladefunktion austauscht und ein
   Manifestfeld setzt. Die Verschlüsselung braucht eine neue
   Abhängigkeit (`cryptography`) und eine unabhängige Review des
   Kryptocodes. **Ob Stufe 2 unmittelbar folgt, ist Entscheidungspunkt E1
   des Spike-Berichts; empfohlen ist unmittelbar.**
7. **Außerhalb gibt es keine API, keine Datenbank, keinen Schreibpfad und
   keinen Weg zurück zum Server.** Die Trennung zwischen lesender Anzeige
   und transaktionalen Funktionen ist Bauart, nicht Regel. Eine
   schreibende Funktion wäre ein anderes System und ein neues ADR.
8. **Geheimnisse:** `ATA_DASHBOARD_PUBLISH_TOKEN` und in Stufe 2
   `ATA_DASHBOARD_EXPORT_PASSPHRASE` in `Secrets` (Schwärzung nach
   [ADR 0044](0044-geheimnisse-an-der-log-senke-schwaerzen.md)); Rotation
   jährlich und bei Verdacht. Hostname, Projektname und Konto stehen in
   keinem Dokument und keinem Workflow des Repositories.
9. **Der Notausschalter** hat fünf Ebenen (Spike-Bericht, Abschnitt 12):
   Seite oder Regel beim Anbieter abschalten, Token widerrufen,
   Exportschritt abschalten, Passphrase wechseln, Sitzungen beenden. Er
   hält den Tageslauf nicht an und löscht nichts auf dem Server.
10. **Erst ein Proof of Concept, dann der Betrieb.** Der PoC läuft mit
    synthetischen Daten (erzeugte Golden-Master-Fälle, Fixture-Anbieter,
    eigene Datenbank), einem Wegwerf-Skript statt Produktcode, einem
    schreibbeschränkten Token und vollständigem Rückbau; er weist nach,
    dass ohne Anmeldung keine Datei erreichbar ist, dass das Token nichts
    anderes kann und dass der Server unverändert bleibt (Spike-Bericht,
    Abschnitt 11). Dieses ADR wird erst nach bestandenem PoC angenommen.
11. **Was nicht entschieden wird:** die Anbieterwahl (PoC, mit
    Nutzungsbedingungen); ein Link in der Telegram-Meldung (der Nachtrag
    zu [ADR 0040](0040-inhalt-der-ergebnismeldung.md) bindet die Frage an
    diese Neubewertung — sie wird mit Stufe 2 entschieden,
    Entscheidungspunkt E5); die Zukunft von ADR 0059 für die Fernwartung
    des Servers (E7).

## Begründung

**Dateien hinter einer Anmeldung sind die kleinste Angriffsfläche, die
ein Dashboard außerhalb des Servers haben kann.** Kein Prozess draußen
rechnet, keine API nimmt Anfragen entgegen, keine Datenbank hält
Zugangsdaten. Was der Anbieter ausliefert, hat der Server erzeugt; was
ein Angreifer draußen findet, ist entweder die Anmeldeseite des Anbieters
— gebaut für Credential Stuffing und Ratenbegrenzung — oder, in Stufe 2,
Chiffrat.

**Der Server bleibt, was ADR 0049 wollte: unerreichbar.** Der Weg dreht
die Richtung um. Der zurückgestellte Overlay-Weg (ADR 0059) ist für den
Zugang **zum Server** die sicherere Antwort — kein öffentlicher Endpunkt,
Ende-zu-Ende, gerätegebunden —, aber er beantwortet eine andere Frage. Für
„beliebige Geräte, einfache Anmeldung" verlangt er genau das, was der
Inhaber ausschließt: Client-Software auf jedem Gerät. Beide Wege schließen
sich nicht aus; dieser hier braucht den anderen nicht.

**Warum Zero-Knowledge die Zielstufe ist und nicht ein Extra:** Stufe 1
allein legt Berichte mit Modelltext, Optionsvorschläge, Kursreihen und
damit die Watchlist im Klartext zu einem Anbieter. Das ist die Lage, die
ADR 0049 mit „solange nichts das eigene Netz verlässt" vermieden hat, und
sie stellt Finnhubs L8 und das Deployment-Gate aus ADR 0022 neu. Stufe 2
beantwortet beides technisch: Ein Anbieter, der nur Chiffrat hält, liest
nichts. Und sie sichert die **Daten** gegen Fälschung — eine Datei, die
nicht mit dem Schlüssel und unter ihrem Pfad verschlüsselt wurde, verwirft
der Browser. Was sie nicht sichert, ist die **Oberfläche**: Wer den Host
kontrolliert, kann die Seite ersetzen, die die Passphrase abfragt. Dagegen
steht die Telegram-Meldung als unabhängige Gegenprobe (Symbole, Scores,
Stufe — [ADR 0047](0047-scores-in-der-ergebnismeldung.md)) und das
Deployment-Protokoll des Anbieters. Diese Grenze ist benannt, nicht
verschwiegen.

**Warum die Anmeldung an der Kante trotz Zero-Knowledge bleibt:** Ohne sie
wäre das Chiffrat öffentlich und die Passphrase der einzige Schutz — ohne
MFA, ohne Ratenbegrenzung, ohne Anmeldeprotokoll. Mit ihr müssen zwei
unabhängige Schichten fallen, bevor jemand Inhalt sieht.

**Warum kein eigener Server draußen:** Er tauschte „nichts zu patchen"
gegen Linux, Proxy und selbst betriebene Anmeldung, für monatliche Kosten
und ohne Zero-Knowledge. **Warum keine gehostete API:** Sie kaufte eine
Aktualität, die der Inhaber nicht verlangt, mit der größten Angriffsfläche
aller Varianten.

**Warum der Server baut und hochlädt, nicht die CI:** Ein Werkzeug, ein
Weg, eine Schreibstelle beim Anbieter. Zwei Schreibstellen — die CI für die
Oberfläche, der Server für die Daten — verdoppeln die Stellen, an denen die
Zugriffsregel vergessen werden kann, und tragen Projektnamen und Token in
die Geheimnisse eines öffentlichen Repositories.

**Warum Isolation wie bei der Meldung:** Das Ergebnis steht in der
Datenbank, bevor der Upload beginnt. Ein Anbieter, der gerade nicht
antwortet, darf keinen Lauf scheitern lassen — dieselbe Regel wie
ADR 0024, aus demselben Grund.

## Konsequenzen

**Positiv**

- Der Server wird durch das Dashboard nicht erreichbarer. Von außen
  antwortet er auf nichts.
- Jedes Gerät mit Browser; kein Client, nichts zu installieren.
- Außerhalb nichts zu patchen; kostenlose Stufen vorhanden; ein
  Anbieterwechsel ist ein Konto, ein Token und ein Vollexport — Stunden.
- Ein Ausfall des Anbieters kostet die Anzeige, nicht den Tageslauf; die
  Telegram-Meldung bleibt.
- Mit Stufe 2 sind Vertraulichkeit gegenüber dem Anbieter und Integrität
  der Daten technisch gesichert, nicht vertraglich.

**Negativ und offen**

- **Stufe 1 legt Klartext zu einem Anbieter.** Die Lizenzfrage (Finnhub
  L8, ADR 0022, IBKR-Bedingungen) ist bis Stufe 2 vom Inhaber zu
  bescheiden — Spike-Bericht, offene Frage O1.
- **Die Anzeige hängt an Host und Token.** Wer eines von beiden hat, kann
  die Seite ersetzen; Stufe 2 schützt die Daten, nicht die Oberfläche.
- **Anwendungsänderungen sind Voraussetzung:** Exporter mit Port, Adapter
  und CLI-Befehl; statischer Datenmodus der Oberfläche; Manifest-Anzeige;
  in Stufe 2 Verschlüsselung auf beiden Seiten mit neuer Abhängigkeit und
  Review. Tage, nicht Stunden — und ein Prototyp im PoC, der nicht gemergt
  wird.
- **Ein Upload-Werkzeug des Anbieters** auf dem Handelsrechner ist möglich
  (Datenweg P2), aber ein Programm mehr; bevorzugt wird der Upload aus
  Python (P1). Wird P2 gewählt, ist ADR 0052 Punkt 2 um „Node als
  Auslieferungswerkzeug" zu ergänzen.
- **Der Export wächst** mit den Berichten; nur Neues wird hochgeladen, eine
  Archivgrenze ist eine spätere Entscheidung.
- **Zwei Anmeldeschritte in Stufe 2** (Anbieter, dann Passphrase); der
  Passwortmanager füllt die zweite.
- **Dokumentation, die nachzuziehen ist:** Doc 14 (neue Stufe K:
  Exportschritt, Anbieterkonsole, Notfallkarte), Doc 13, Doc 10 §3, §6.15,
  §13, §14, Doc 11 (der Datenbaum als zweiter Vertrag derselben
  Antwortschemata), gegebenenfalls ADR 0052 Punkt 2, README.

**Was dieses ADR ablöst, sobald es angenommen ist:** die Aussage „keine
Exposition, keine eigene Authentifizierung" aus ADR 0049 wird zu „der
Server bleibt ohne Exposition; das Dashboard läuft zusätzlich außerhalb,
hinter der Anmeldung des Anbieters". ADR 0052 bleibt für die
LAN-Auslieferung in Kraft und bekommt mit dem statischen Datenmodus eine
zweite Auslieferung; ADR 0053 bleibt unverändert — außerhalb gibt es
keine API. ADR 0059 wird für das Dashboard nicht weiterverfolgt; ob es für
die Fernwartung des Servers wieder aufgenommen wird, ist eine eigene
Frage. ADR 0049 wird nicht rückwirkend geändert.
