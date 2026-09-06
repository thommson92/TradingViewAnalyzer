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
- **Der Webprozess protokolliert heute ohne Schwärzung.** Die Log-Senke mit
  der Schwärzung aus [ADR 0044](0044-geheimnisse-an-der-log-senke-schwaerzen.md)
  wird nur vom CLI aufgesetzt; `main.py` und `build_app()` konfigurieren
  kein Logging. Das ist unabhängig vom Fernzugang ein Befund und wird mit
  ihm dringlicher.

Untersucht wurden sechs Wege: VPN am Router, VPN-Server auf dem
Windows-Server, ein identitätsgebundenes Overlay-Netz (WireGuard-basiertes
Mesh mit Koordinationsdienst, Anmeldung über einen Identitätsanbieter mit
MFA, Zugriffsregeln je Gerät, Verbindungsaufbau vom Server nur nach außen),
ein Identity-Aware Proxy mit ausgehendem Tunnel (Zero Trust Network
Access), ein Reverse Proxy mit TLS und starker Authentifizierung auf dem
Server hinter einer Portweiterleitung und ein selbst betriebener
Bastion-Server mit Rücktunnel — samt Kombinationen. Die vollständige
Bewertung steht im Spike-Bericht, Abschnitte 6 und 7.

## Entscheidung

1. **Das Dashboard wird nicht öffentlich erreichbar.** Es bekommt keinen
   öffentlichen Hostnamen für den Zugriff und keine eingehende Freigabe —
   weder am Windows-Server noch am Router. Die Frage „extern erreichbar"
   wird als **privater Fernzugang für die registrierten Geräte des
   Nutzers** beantwortet, nicht als Veröffentlichung im Internet.
2. **Der Fernzugang läuft über ein identitätsgebundenes Overlay-Netz.**
   Der Server baut Verbindungen ausschließlich nach außen auf; der Agent
   lauscht auf einem UDP-Port, antwortet aber nur auf gültige Handshakes
   registrierter Schlüssel — unauthentifizierte Pakete bleiben
   unbeantwortet. Seine Portzuordnung am Router (UPnP, NAT-PMP) wird
   abgeschaltet. Jedes Gerät des Nutzers wird über den Identitätsanbieter
   registriert, dessen Konto **ausschließlich** phishing-resistente
   Faktoren zulässt (Passkey oder Hardware-Schlüssel; Passwort-, SMS- und
   TOTP-Rückfall abgeschaltet, Wiederherstellung nur über offline
   verwahrte Codes), und erhält einen eigenen, ablaufenden Geräteschlüssel.
   Eine Zugriffsregel erlaubt **nur diesen Geräten** den Port des
   Dashboards auf dem Server; alles Übrige ist verweigert. Ein Gerät, das
   nicht registriert ist, erreicht nicht einmal einen Anmeldedialog.
3. **Der Koordinationsdienst allein darf keinen Knoten hinzufügen.** Er
   verteilt Schlüssel **und** Regeln; ein kompromittierter Dienst könnte
   sonst einen fremden Knoten einschleusen und die Regel weiten. Deshalb
   gilt als K.-o.-Kriterium für den Anbieter: **Signierung neuer Knoten
   durch einen bestehenden Knoten des Nutzers** (mehrere Anbieter bieten
   das an; alternativ selbst gehostete Koordination). Und als
   anbieterunabhängige zweite Ebene verwirft die **Windows-Firewall auf
   der Overlay-Schnittstelle eingehend alles außer dem Dashboard-Port**;
   die Standardregeln für RDP, SMB und WinRM dürfen dort nicht greifen.
   Selbst eine geweitete Regel beim Anbieter erreicht damit nichts
   anderes als das Dashboard.
4. **Der Dienst bindet nicht mehr an alle Schnittstellen.** Er lauscht
   auf der Loopback- und der Overlay-Schnittstelle; die Firewallregel
   für den Dashboard-Port gilt nur für die Overlay-Schnittstelle. Die
   LAN-Freigabe im privaten Profil aus Doc 14, Stufe J, Schritt 4
   **entfällt**: Ein Weg statt zwei, und ein Tablet im heimischen WLAN
   nimmt denselben Weg wie das Smartphone unterwegs. Das **ersetzt**
   Punkt 3 aus [ADR 0052](0052-dashboard-als-statischer-export.md); der
   dort beschlossene Autostart-Eintrag bleibt, seine Bindung ändert sich.
5. **Der Dienst wird gehärtet, unabhängig vom Weg.** Eigenes lokales
   Dienstkonto ohne Administratorrechte für den Autostart-Eintrag; eigene
   PostgreSQL-Rolle mit ausschließlich Leserechten; Prüfung des
   `Host`-Headers gegen Overlay-Name, Overlay-Adresse und Loopback
   (Schutz gegen DNS-Rebinding aus dem Browser eines registrierten
   Geräts); `/docs`, `/redoc` und `/openapi.json` außerhalb der
   Entwicklung abgeschaltet; Sicherheits-Header (eine
   `Content-Security-Policy` mit `frame-ancestors 'none'`,
   `X-Content-Type-Options`, `Referrer-Policy`); Logging **mit** der
   Schwärzung aus ADR 0044 auch im Webprozess, Zugriffsprotokoll in eine
   Datei mit Rotation, ohne Geheimnisse und ohne Anfrageinhalte;
   Lastbegrenzung (Gleichzeitigkeit, Verbindungs-Timeouts, niedrige
   Prozesspriorität), damit ein fehlerhafter oder feindlicher Client den
   Tageslauf nicht ausbremst; der Dashboard-Prozess erhält nur das eine
   Geheimnis, das er braucht — die Datenbank-URL der Leserolle — und nicht
   die ganze `.env`. Das sind Anwendungsänderungen und ein eigenes
   Feature; sie stehen als Bedingung hier, nicht als Umsetzung.
6. **Die API bleibt lesend, und das Dashboard bekommt in dieser Stufe keine
   eigene Anmeldung.** `ATA_SESSION_SECRET` bleibt reserviert. Das ist eine
   bewusste Abweichung von Doc 10 §13, das auch für ein nicht öffentliches
   Dashboard einen Login verlangt; die Begründung steht unten. **Sollten je
   schreibende Funktionen kommen** — Läufe auslösen, Konfiguration ändern,
   irgendetwas, das eine Order oder ein Modell berührt —, ist das ein
   neues ADR mit eigener Anmeldung im Dienst, Step-up-Authentifizierung je
   Aktion, getrennter Berechtigung für Schreibpfade, unveränderbarem
   Audit-Protokoll und einem eigenen Host für den Dienst. Die Trennung
   zwischen lesender Anzeige und transaktionalen Funktionen ist damit
   festgeschrieben: Es gibt nur die erste.
7. **Der Notausschalter ist Teil der Einrichtung, nicht ein Nachtrag.** Der
   Fernzugang wird an drei Stellen unabhängig voneinander gekappt: Sperren
   oder Löschen des Server-Knotens im Koordinationsdienst (wirkt für neue
   Verbindungen sofort, für bestehende binnen einer im PoC gemessenen
   Frist; von jedem Gerät aus), Anhalten des Overlay-Dienstes und des
   Autostart-Eintrags auf dem Server, Löschen der Firewallregel. Die
   Reihenfolge und die Prüfung, dass sie gewirkt haben, stehen in Doc 14.
8. **Erst ein Proof of Concept, dann der Betrieb.** Der PoC läuft ohne
   Produktivdaten und ohne produktive Zugangsdaten: eigene Testinstanz auf
   eigenem Port, eigene Datenbank mit ausschließlich synthetischen Daten
   aus den Fixture-Anbietern, nur Testgeräte in der Zugriffsregel,
   vollständiger Rückbau. Die Abnahmekriterien und Negativtests stehen im
   Spike-Bericht, Abschnitt 11 — darunter der Nachweis, dass eine
   testweise geweitete Anbieterregel an der Windows-Firewall scheitert,
   dass ein gesperrtes Gerät auch bei offener Verbindung binnen gemessener
   Zeit getrennt wird und dass die Anmeldung am Identitätsanbieter ohne
   Passkey nicht möglich ist. Der produktive Fernzugang wird als eigenes
   Feature umgesetzt, nachdem der PoC bestanden ist — und erst dann wird
   dieses ADR angenommen.
9. **Was nicht entschieden wird:** kein Container, kein Reverse Proxy
   (Punkt 1 aus ADR 0052 bleibt — es gibt keinen öffentlichen Endpunkt, den
   ein Proxy schützen müsste); keine Anbieterwahl (sie gehört in den PoC,
   mit Prüfung der Nutzungsbedingungen); und **kein Link in der
   Ergebnismeldung** — der Nachtrag zu
   [ADR 0040](0040-inhalt-der-ergebnismeldung.md) bindet die Link-Frage
   ausdrücklich an diese Neubewertung, sie bleibt hier aber bewusst offen:
   Ein Overlay-Name löst nur auf registrierten Geräten auf, ob er in eine
   Nachricht gehört, die das eigene Netz verlässt, ist eine eigene
   Abwägung gegen ADR 0040 und wird mit Stufe 2 entschieden.

## Begründung

**Die kleinste Angriffsfläche ist die, die nicht antwortet.** Ein
Overlay-Netz mit Verbindungsaufbau nach außen öffnet am Handelsrechner
keine Freigabe und am Router keine Weiterleitung; der einzige lauschende
Port des Agenten schweigt gegenüber jedem Paket ohne gültigen
Geräteschlüssel. Es gibt keinen Anmeldedialog, den man mit Passwörtern
bombardieren, und keine TLS-Endstelle, die man falsch konfigurieren könnte.
Brute Force und Credential Stuffing zielen auf den Identitätsanbieter, der
dafür gebaut ist — und der mit Passkey-Pflicht keinen schwächeren Rückfall
mehr anbietet —, nicht auf einen Python-Prozess neben der TWS. Das ist die
Variante, die alle fünf Vorzugskriterien der Aufgabenstellung erfüllt:
keine eingehenden Freigaben, Dienst nur an internen Schnittstellen,
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
nicht die beste.** Er erfüllt dieselben fünf Vorzugskriterien ohne
eingehende Freigabe — aber er gibt dem Dashboard einen öffentlichen
Hostnamen mit öffentlicher Anmeldeseite, verlegt die TLS-Endstelle zum
Anbieter, der damit den Klartext der Analyseergebnisse sieht (eine Frage
an Finnhubs L8, die der Overlay-Weg gar nicht erst stellt, weil dort Ende
zu Ende verschlüsselt wird), und verlangt, dass der Dienst das
Identitätstoken des Anbieters selbst prüft — sonst schützt nur die
Konfiguration des Tunnels. Er bleibt der Ausweichweg, falls
Client-Software auf den Endgeräten nicht in Frage kommt.

**VPN am Router oder VPN-Server auf dem Windows-Server** öffnen eine
eingehende Freigabe (UDP) — am Router noch vertretbar, am Handelsrechner
nicht —, kennen meist nur ein geteiltes Geheimnis oder ein Schlüsselpaar
ohne Identitätsanbieter, keine MFA und keine Zugriffsregel je Gerät, und
lassen ein verbundenes Gerät im gesamten Heimnetz stehen statt an einem
Port. Der Overlay-Weg ist dasselbe Prinzip mit Identität, Gerätebindung
und Least Privilege. **Ein eigener Bastion-Server** löst die Portfrage,
tauscht den Koordinationsdienst gegen einen Hoster als Vertrauensinstanz
und behält alle Selbstbetriebspflichten des Reverse Proxy.

**Der Preis des Overlay-Wegs ist eine Abhängigkeit, und sie wird nicht
kleingeredet.** Der Koordinationsdienst ist ein Drittanbieter, sein Agent
läuft auf dem Server als Dienst mit Systemrechten, und er ist der
Vertrauensanker für Schlüssel und Regeln — ein kompromittierter
Koordinationsdienst wäre nicht ein Mitleser, sondern ein möglicher
Endpunkt. Genau deshalb sind Knotensignierung und die Windows-Firewall als
zweite Ebene Bedingungen (Punkt 3) und nicht Empfehlungen: Mit ihnen
erreicht ein eingeschleuster Knoten nichts, und eine geweitete Regel
endet am Dashboard-Port. Dagegen stehen außerdem: Der Datenverkehr ist
Ende zu Ende verschlüsselt, Relais sehen nur Chiffrat; ein Ausfall des
Anbieters kostet den Fernzugang, nicht den Tageslauf — der Dispatcher
braucht das Overlay nicht, und die Telegram-Meldung bleibt; und die
Alternative ist nicht „keine Abhängigkeit", sondern ein selbst
betriebener Bastion-Server mit selbst betriebener Anmeldung — mehr
Betrieb, gleiche Vertrauensfrage, anderer Anbieter. Wer den
Koordinationsdienst nicht will, kann ihn selbst hosten; das ist ein
eigener Betriebsaufwand und wird im PoC nicht verfolgt.

**Warum keine Anmeldung im Dienst, obwohl Doc 10 §13 sie auch für ein
nicht öffentliches Dashboard verlangt:** Doc 10 §13 fordert „Login,
sichere Passwortspeicherung, Sitzungsablauf" und ist bei Widersprüchen
maßgeblich ([ADR 0001](0001-dokumentenhierarchie.md)); dieses ADR weicht
für die lesende Stufe **bewusst** davon ab. Die Anmeldung mit MFA findet
statt — an der Netzgrenze, je Gerät, bevor ein Paket den Dienst erreicht.
Drei Einwände wurden abgewogen. Erstens braucht eine Passkey-Anmeldung
keinen Passwortspeicher; sie brächte aber Sitzungsverwaltung,
Cookie-Handhabung und eine zweite Regelstelle in eine Anwendung, die
heute keinen Schreibpfad hat. Zweitens ist der Gegner nicht nur ein
registriertes Gerät in fremder Hand, sondern auch eine bösartige Webseite
oder App auf dem eigenen, entsperrten Gerät, solange das Overlay verbunden
ist — dagegen wirken die Host-Header-Prüfung und HTTPS im Tunnel (Punkt 5,
Spike-Bericht 8.3), nicht ein Login, den der Browser ohnehin hielte.
Drittens liegt die Zugriffskontrolle damit an einer einzigen Stelle, der
Regel beim Anbieter — abgefangen durch die Windows-Firewall als zweite
Ebene (Punkt 3). Der verbleibende Schaden ist Lesen. Das Verhältnis
rechtfertigt heute keine zweite Anmeldeschicht in der Anwendung. Diese
Abwägung ist umkehrbar und wird im Spike-Bericht als Entscheidungspunkt
geführt; sie kehrt sich sicher um, sobald es einen Schreibpfad gibt
(Punkt 6).

## Konsequenzen

**Positiv**

- Keine eingehende Freigabe am Handelsrechner, keine Weiterleitung am
  Router, kein öffentlicher Zugangsname. Von außen antwortet der Server
  wie heute auf nichts.
- Der Zugriff ist auf benannte Geräte eines benannten Nutzers beschränkt;
  Finnhub L8 und das Deployment-Gate aus ADR 0022 bleiben gewahrt, weil
  niemand außer dem Nutzer etwas sieht.
- Der Notausschalter wirkt sofort und von unterwegs.
- Die Härtung aus Punkt 5 nützt auch im LAN-Betrieb; sie ist nicht an
  den Fernzugang gebunden — und die fehlende Schwärzung im Webprozess wird
  ohnehin behoben.

**Negativ und offen**

- **Client-Software auf jedem Gerät**, das zugreifen soll, und ein Konto
  bei einem Identitätsanbieter, das auf Passkeys allein steht. Ein fremder
  Browser kommt nicht heran — das ist gewollt, aber unbequem.
- **Sperre am Identitätsanbieter heißt kein Fernzugang.** Der
  Wiederherstellungsweg (Offline-Codes, zweiter Schlüssel) gehört
  abgelegt, bevor der erste Knoten registriert wird. Die Sitzung der
  Anbieterkonsole auf dem Telefon ist selbst ein Schutzgut: Sie
  kontrolliert Notausschalter, Gerätefreigabe und Regeln.
- **Ein Dienst mit Systemrechten mehr** auf dem Server (der Overlay-Agent),
  vom Anbieter gepatcht. Automatische Aktualisierung ist einzuschalten; das
  Pflegeprotokoll in Doc 14 wächst um den Agenten und um die
  Ablauffristen der Geräteschlüssel.
- **HTTPS im Tunnel hat einen Preis:** Zertifikate für Overlay-Namen
  kommen von öffentlichen Zertifizierungsstellen, und die Namen landen in
  öffentlichen Transparenzprotokollen; für den Nachweis legen Anbieter
  öffentliche DNS-Einträge auf die Overlay-Adresse. Der Name ist dann
  auffindbar, die Adresse von außen unerreichbar. Knoten- und Netznamen
  sind deshalb nichtssagend zu wählen.
- **Der Web-Stack wird erreichbar** — wenn auch nur für eigene Geräte.
  Meldungen aus `audit.yml` zu `uvicorn`, `starlette`, `fastapi` und `h11`
  sind künftig binnen Tagen zu bescheiden, nicht im Quartalsturnus.
- **Die Windows-Firewall filtert Loopback-Verkehr nicht.** Ein Dienstkonto
  ist damit eine Grenze zu Dateien, Aufgaben und Datenbankrechten — nicht
  zur TWS an `127.0.0.1:7496`. Der PoC bestätigt das; die harte Grenze
  wäre ein eigener Host für das Dashboard. Das ist für die lesende Stufe
  nicht gefordert und bleibt als Ausbaustufe vorgemerkt — Bedingung für
  jeden Schreibpfad.
- **Eine Anwendungsänderung ist Voraussetzung** (Punkt 5): Bindung,
  Host-Prüfung, Header, Abschalten der API-Dokumentation, Logging mit
  Schwärzung, eigene Umgebung für den Dashboard-Prozess, Zugriffsprotokoll
  in Datei, Lastbegrenzung. Ohne sie wird der Fernzugang nicht produktiv
  geschaltet.
- **Dokumentation, die nachzuziehen ist:** Doc 14 Stufe J (Bindung,
  Firewallregeln, Dienstkonto, Notfallkarte, neue Stufe für den
  Fernzugang), Doc 10 §3 („F12, unentschieden"), §13 und §14, Doc 13,
  Doc 11 (Satz „nur im eigenen Netz erreichbar"), README (der Absatz zu
  `POST /api/v1/analysis-runs` ist seit ADR 0053 überholt).

**Was dieses ADR ablöst, sobald es angenommen ist:** die Aussage „keine
Exposition" aus ADR 0049 wird zu „keine öffentliche Exposition; privater
Fernzugang über das Overlay-Netz"; Punkt 3 aus ADR 0052 (Bindung an die
LAN-Schnittstelle, Firewallregel im privaten Profil) wird durch Punkt 4
oben ersetzt. ADR 0049 und ADR 0052 werden nicht rückwirkend geändert.
