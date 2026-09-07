// @vitest-environment node
//
// Die Browserhaelfte der Zero-Knowledge-Verschluesselung (ADR 0060, Stufe 2).
//
// `node` statt `jsdom`: Die Funktionen brauchen WebCrypto und
// `DecompressionStream`, und jsdom bringt beides nicht mit. Der Browser hat
// beides -- geprueft wird hier dieselbe Standard-API.
//
// Der wichtigste Test in dieser Datei entschluesselt eine Datei, die die
// **Serverhaelfte** erzeugt hat. Ohne ihn faende ein auseinandergelaufenes
// Format erst dort statt, wo jemand vor einem leeren Dashboard steht.

import { describe, expect, it } from 'vitest';

import vertrag from './__fixtures__/zero-knowledge.json';
import {
  DatenbaumFehler,
  alsHex,
  ausHex,
  entschluessele,
  leiteSchluesselAb,
  opakerName,
  pruefeKopf,
  type Schluessel,
} from './datenbaum';

async function schluesselDesVertrags(passphrase = vertrag.passphrase): Promise<Schluessel> {
  return await leiteSchluesselAb(
    passphrase,
    ausHex(vertrag.salt),
    vertrag.iterations,
    vertrag.tree_id,
    vertrag.format,
  );
}

describe('Vertrag mit der Serverhaelfte', () => {
  it('entschluesselt, was Python verschluesselt hat', async () => {
    const klartext = await entschluessele(
      await schluesselDesVertrags(),
      vertrag.pfad,
      ausHex(vertrag.chiffrat),
    );
    expect(new TextDecoder().decode(klartext)).toBe(vertrag.klartext);
  });

  it('leitet denselben opaken Dateinamen ab', async () => {
    const schluessel = await schluesselDesVertrags();
    expect(await opakerName(schluessel.namen, vertrag.pfad)).toBe(vertrag.dateiname);
  });

  it('rechnet dieselbe Pruefsumme des Klartexts', async () => {
    const klartext = await entschluessele(
      await schluesselDesVertrags(),
      vertrag.pfad,
      ausHex(vertrag.chiffrat),
    );
    const gemessen = alsHex(await crypto.subtle.digest('SHA-256', klartext.slice().buffer));
    expect(gemessen).toBe(vertrag.klartext_sha256);
  });
});

describe('Was scheitern muss', () => {
  it('scheitert bei falscher Passphrase', async () => {
    await expect(
      entschluessele(
        await schluesselDesVertrags('falsch'),
        vertrag.pfad,
        ausHex(vertrag.chiffrat),
      ),
    ).rejects.toThrow(DatenbaumFehler);
  });

  it('scheitert unter einem fremden Pfad', async () => {
    // Der Vertauschungsschutz: Der Chart einer Aktie darf nicht unter dem
    // Namen einer anderen lesbar sein.
    await expect(
      entschluessele(
        await schluesselDesVertrags(),
        'data/stocks/MSFT/chart.json',
        ausHex(vertrag.chiffrat),
      ),
    ).rejects.toThrow(DatenbaumFehler);
  });

  it('scheitert nach einem veraenderten Byte', async () => {
    const chiffrat = ausHex(vertrag.chiffrat);
    const letztes = chiffrat.length - 1;
    chiffrat[letztes] = (chiffrat[letztes] ?? 0) ^ 0x01;
    await expect(
      entschluessele(await schluesselDesVertrags(), vertrag.pfad, chiffrat),
    ).rejects.toThrow(DatenbaumFehler);
  });
});

describe('Der Klartextkopf wird geprueft, nicht befolgt', () => {
  const gueltig = {
    format: 1,
    kdf: 'PBKDF2-HMAC-SHA256',
    iterations: 600000,
    salt: 'a'.repeat(64),
    cipher: 'AES-256-GCM',
    tree_id: 'baum-1',
    manifest: 'b'.repeat(32),
  };

  it('nimmt einen gueltigen Kopf an', () => {
    expect(pruefeKopf(gueltig).tree_id).toBe('baum-1');
  });

  it('lehnt herabgesetzte Rundenzahlen ab', () => {
    // Der Angriff, gegen den diese Pruefung steht: Wer den Kopf schreiben
    // darf, drehte die Ableitung sonst auf tausend Runden herunter.
    expect(() => pruefeKopf({ ...gueltig, iterations: 1000 })).toThrow(/Ableitungsrunden/);
  });

  it('lehnt ein anderes Verfahren ab', () => {
    expect(() => pruefeKopf({ ...gueltig, cipher: 'AES-128-CBC' })).toThrow(/Verfahren/);
  });

  it('lehnt ein unbekanntes Format ab', () => {
    expect(() => pruefeKopf({ ...gueltig, format: 99 })).toThrow(/Format/);
  });

  it('lehnt ein zu kurzes Salt ab', () => {
    expect(() => pruefeKopf({ ...gueltig, salt: 'ab' })).toThrow(/Salt/);
  });

  it('lehnt einen Kopf ohne Manifest ab', () => {
    expect(() => pruefeKopf({ ...gueltig, manifest: '' })).toThrow(/Manifest/);
  });

  it('lehnt einen Kopf ab, der gar kein Objekt ist', () => {
    // Ohne diese Pruefung wirft der naechste Feldzugriff einen TypeError der
    // Laufzeitumgebung, und die Oberflaeche zeigte ihn im Wortlaut.
    expect(() => pruefeKopf(null)).toThrow(DatenbaumFehler);
    expect(() => pruefeKopf('kein Objekt')).toThrow(DatenbaumFehler);
  });

  it('lehnt ein Salt ab, das kein Hex ist', () => {
    // `ausHex` machte aus 64 unzulaessigen Zeichen stillschweigend 32
    // Nullbytes -- und die Oberflaeche meldete danach "Passphrase falsch"
    // fuer einen Fehler, der ganz woanders lag.
    expect(() => pruefeKopf({ ...gueltig, salt: 'z'.repeat(64) })).toThrow(/Salt/);
    expect(() => pruefeKopf({ ...gueltig, salt: 'a'.repeat(65) })).toThrow(/Salt/);
  });

  it('lehnt unglaubwuerdig viele Runden ab', () => {
    // Nach oben offen waere die Rundenzahl ein Knopf zum Aufhaengen des Tabs.
    expect(() => pruefeKopf({ ...gueltig, iterations: 1_000_000_000_000 })).toThrow(
      /Unglaubwuerdig/,
    );
  });

  it('lehnt eine Baumkennung mit Zeilenumbruch ab', () => {
    // Der Umbruch trennt die Bestandteile der Zusatzdaten; eine Kennung, die
    // selbst einen enthaelt, machte die Kodierung mehrdeutig.
    expect(() => pruefeKopf({ ...gueltig, tree_id: 'a\nb' })).toThrow(/Kennung/);
  });
});

describe('Hex-Werte werden streng gelesen', () => {
  it('weist unzulaessige Zeichen zurueck, statt Nullbytes zu liefern', () => {
    expect(() => ausHex('z'.repeat(64))).toThrow(DatenbaumFehler);
  });

  it('weist eine ungerade Laenge zurueck', () => {
    expect(() => ausHex('abc')).toThrow(DatenbaumFehler);
  });
});

describe('Hex', () => {
  it('geht hin und zurueck', () => {
    const bytes = new Uint8Array([0, 1, 15, 16, 254, 255]);
    expect(ausHex(alsHex(bytes.slice().buffer))).toEqual(bytes);
  });
});
