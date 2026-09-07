// @vitest-environment node
//
// Das Dashboard ausserhalb des Servers liest Dateien statt einer API
// (ADR 0060). Diese Tests pruefen die zweite Herkunft in `api.ts`: dass jede
// Funktion die richtige Datei nimmt, dass geblaettert und gefiltert wird wie
// in der API -- und dass eine Datei, die nicht zu diesem Stand gehoert,
// nicht angezeigt wird.
//
// `node` statt `jsdom`: Die Pruefsumme rechnet WebCrypto.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getAktienBacktest,
  getChart,
  getReport,
  getRun,
  listMessungen,
  listRunReports,
  listRuns,
  listStockReports,
  setzeDatenbaum,
  type AnalysisRun,
} from '@/lib/api';
import { Datenbaum, alsHex, type Manifest } from '@/lib/datenbaum';

const LAUF_A: AnalysisRun = {
  id: 'lauf-a',
  status: 'COMPLETED',
  started_at: '2026-09-05T16:45:00+00:00',
  completed_at: '2026-09-05T17:20:00+00:00',
  number_of_stocks: 2,
  candidates_found: 1,
  error_message: null,
};
const LAUF_B: AnalysisRun = { ...LAUF_A, id: 'lauf-b', status: 'FAILED' };

async function baumMit(dateien: Record<string, unknown>): Promise<Datenbaum> {
  const kodiert = new Map<string, Uint8Array>();
  const hashes: Record<string, string> = {};
  for (const [pfad, inhalt] of Object.entries(dateien)) {
    const bytes = new TextEncoder().encode(JSON.stringify(inhalt));
    kodiert.set(pfad, bytes);
    hashes[pfad] = alsHex(await crypto.subtle.digest('SHA-256', bytes.slice().buffer));
  }
  vi.stubGlobal('fetch', (adresse: string) => {
    const bytes = kodiert.get(adresse.replace(/^\//, ''));
    if (bytes === undefined) {
      return Promise.resolve({ ok: false, status: 404 });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      arrayBuffer: () => Promise.resolve(bytes.slice().buffer),
    });
  });
  const manifest: Manifest = {
    format: 1,
    export_id: 'export-1',
    exported_at: '2026-09-07T21:00:00+00:00',
    run_id: 'lauf-a',
    run_started_at: LAUF_A.started_at,
    run_completed_at: LAUF_A.completed_at,
    run_status: 'COMPLETED',
    application_version: '0.1.0',
    report_schema_version: 'report-v2',
    signal_rule_version: 'g1',
    symbols: { AAPL: 'AAPL', 'BRK B': 'BRK-B' },
    counts: {},
    stocks_without_chart: [],
    files: hashes,
  };
  return new Datenbaum(manifest, null);
}

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_DATENMODUS', 'statisch');
});

afterEach(() => {
  setzeDatenbaum(null);
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('Blaettern und Filtern geschehen im Browser', () => {
  it('liefert eine Seite mit der Gesamtzahl', async () => {
    setzeDatenbaum(await baumMit({ 'data/analysis-runs.json': [LAUF_A, LAUF_B] }));

    const seite = await listRuns({ limit: 1, offset: 0 });

    expect(seite.items).toEqual([LAUF_A]);
    expect(seite.total).toBe(2);
    expect(seite.limit).toBe(1);
  });

  it('zaehlt nach dem Filtern, nicht davor', async () => {
    // Sonst zeigte die Oberflaeche "2 von 2", waehrend nur einer passt --
    // dieselbe Zusage wie ``count(status=...)`` in der API.
    setzeDatenbaum(await baumMit({ 'data/analysis-runs.json': [LAUF_A, LAUF_B] }));

    const seite = await listRuns({ status: ['COMPLETED'] });

    expect(seite.items).toEqual([LAUF_A]);
    expect(seite.total).toBe(1);
  });

  it('nimmt dieselben Voreinstellungen wie die API', async () => {
    setzeDatenbaum(await baumMit({ 'data/analysis-runs.json': [LAUF_A] }));

    const seite = await listRuns();

    expect(seite.limit).toBe(25);
    expect(seite.offset).toBe(0);
  });
});

describe('Jede Funktion nimmt ihre Datei', () => {
  it('holt Laufdetail, Berichtsliste und Bericht', async () => {
    setzeDatenbaum(
      await baumMit({
        'data/analysis-runs/lauf-a.json': { ...LAUF_A, earnings_excluded: 0 },
        'data/analysis-runs/lauf-a/reports.json': [{ report_id: 'b1', symbol: 'AAPL' }],
        'data/reports/b1.json': { lauf_id: 'lauf-a' },
      }),
    );

    expect((await getRun('lauf-a')).id).toBe('lauf-a');
    expect(await listRunReports('lauf-a')).toHaveLength(1);
    expect((await getReport('b1')).lauf_id).toBe('lauf-a');
  });

  it('holt Chart, Backtest und Berichte einer Aktie', async () => {
    setzeDatenbaum(
      await baumMit({
        'data/stocks/AAPL/chart.json': { symbol: 'AAPL' },
        'data/stocks/AAPL/backtest.json': { symbol: 'AAPL', measurement: null },
        'data/stocks/AAPL/reports.json': [{ report_id: 'b1' }],
      }),
    );

    expect((await getChart('AAPL')).symbol).toBe('AAPL');
    expect((await getAktienBacktest('AAPL')).symbol).toBe('AAPL');
    expect((await listStockReports('AAPL')).total).toBe(1);
  });

  it('uebersetzt ein Symbol in seinen Verzeichnisnamen', async () => {
    // `BRK B` ist ein gueltiges Symbol und kein gueltiger Pfadbestandteil.
    // Die Zuordnung kommt aus dem Manifest -- die Oberflaeche setzt die Regel
    // nicht ein zweites Mal um.
    setzeDatenbaum(await baumMit({ 'data/stocks/BRK-B/chart.json': { symbol: 'BRK B' } }));

    expect((await getChart('BRK B')).symbol).toBe('BRK B');
  });

  it('holt die Messungen', async () => {
    setzeDatenbaum(
      await baumMit({ 'data/options-backtests.json': [{ measurement_id: 'm1' }] }),
    );

    expect(await listMessungen()).toHaveLength(1);
  });
});

describe('Was nicht angezeigt wird', () => {
  it('lehnt eine Datei ab, deren Pruefsumme abweicht', async () => {
    // Der Schutz gegen eine untergeschobene aeltere Fassung: Sie
    // entschluesselt sich einwandfrei und faellt erst hier auf.
    const baum = await baumMit({ 'data/analysis-runs.json': [LAUF_A] });
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
        ok: true,
        status: 200,
        arrayBuffer: () =>
          Promise.resolve(new TextEncoder().encode('[{"id":"gefaelscht"}]').slice().buffer),
      }),
    );
    setzeDatenbaum(baum);

    await expect(listRuns()).rejects.toThrow(/Pruefsumme/);
  });

  it('meldet eine unbekannte Aktie, statt eine leere Ansicht zu zeigen', async () => {
    setzeDatenbaum(await baumMit({}));

    await expect(getChart('UNBEKANNT')).rejects.toThrow(/steht nicht in diesem Stand/);
  });

  it('gibt fuer eine aeltere Messung nicht stillschweigend die juengste', async () => {
    // Die schlimmere Antwort waere: Zahlen, die richtig aussehen und zu einer
    // anderen Messung gehoeren.
    setzeDatenbaum(
      await baumMit({
        'data/stocks/AAPL/backtest.json': {
          symbol: 'AAPL',
          measurement: { measurement_id: 'neueste' },
        },
      }),
    );

    await expect(getAktienBacktest('AAPL', 'aeltere')).rejects.toThrow(/juengste Messung/);
  });

  it('meldet einen fehlenden Stand, statt eine leere Liste zu liefern', async () => {
    await expect(listRuns()).rejects.toThrow(/noch nicht geoeffnet/);
  });
});
