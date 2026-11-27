import assert from 'node:assert/strict';
import { before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { runnerImport } from 'vite';

const load = async (path) =>
  (await runnerImport(fileURLToPath(new URL(path, import.meta.url)), { configFile: false, logLevel: 'silent' })).module;

let api;
before(async () => {
  api = await load('../src/tutor/api.ts');
});

function fakeFetch(status, body) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    if (status === 'network') throw new TypeError('Failed to fetch');
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  return Object.assign(fn, { calls });
}

describe('análisis con Tutor: POST /api/tutor/analyses (sección 16.4)', () => {
  const GAME_ID = '33333333-3333-4333-8333-333333333333';
  const ANALYSIS_ID = '44444444-4444-4444-8444-444444444444';

  const sampleStatus = {
    analysisId: ANALYSIS_ID,
    gameId: GAME_ID,
    status: 'pending',
    engineVersion: 'Stockfish 15.1',
    depth: 10,
    language: 'es',
    detailLevel: 'standard',
    createdAt: '2026-11-03T20:00:00Z',
    updatedAt: '2026-11-03T20:00:00Z',
    error: null,
    retryable: false,
  };

  test('202 = análisis creado/reactivado con éxito', async () => {
    const f = fakeFetch(202, sampleStatus);
    const res = await api.requestAnalysis(GAME_ID, undefined, f);

    assert.equal(res.kind, 'ok');
    assert.equal(res.created, true);
    assert.equal(res.status.analysisId, ANALYSIS_ID);
    assert.equal(f.calls[0].url, '/api/tutor/analyses');
    assert.equal(f.calls[0].init.method, 'POST');
    assert.equal(f.calls[0].init.credentials, 'same-origin');
  });

  test('200 = análisis ya existente devuelto', async () => {
    const f = fakeFetch(200, { ...sampleStatus, status: 'completed' });
    const res = await api.requestAnalysis(GAME_ID, undefined, f);

    assert.equal(res.kind, 'ok');
    assert.equal(res.created, false);
    assert.equal(res.status.status, 'completed');
  });

  test('401 = sesión no válida', async () => {
    const f = fakeFetch(401, { error: { code: 'UNAUTHORIZED', message: 'No auth' } });
    const res = await api.requestAnalysis(GAME_ID, undefined, f);
    assert.equal(res.kind, 'unauthenticated');
  });

  test('404 = partida no encontrada o no visible', async () => {
    const f = fakeFetch(404, { error: { code: 'GAME_NOT_FOUND', message: 'No existe la partida' } });
    const res = await api.requestAnalysis(GAME_ID, undefined, f);
    assert.equal(res.kind, 'not_found');
  });

  test('409 GAME_NOT_FINISHED = partida no terminada', async () => {
    const f = fakeFetch(409, { error: { code: 'GAME_NOT_FINISHED', message: 'En curso' } });
    const res = await api.requestAnalysis(GAME_ID, undefined, f);
    assert.equal(res.kind, 'not_finished');
  });

  test('409 GAME_NOT_ANALYZABLE = partida sin jugadas o expirada', async () => {
    const f = fakeFetch(409, { error: { code: 'GAME_NOT_ANALYZABLE', message: 'No analizable' } });
    const res = await api.requestAnalysis(GAME_ID, undefined, f);
    assert.equal(res.kind, 'not_analyzable');
  });
});

describe('estado del análisis: GET /api/tutor/analyses/{id}', () => {
  const ANALYSIS_ID = '44444444-4444-4444-8444-444444444444';

  test('200 = devuelve AnalysisStatus', async () => {
    const f = fakeFetch(200, {
      analysisId: ANALYSIS_ID,
      gameId: '33333333-3333-4333-8333-333333333333',
      status: 'processing',
      engineVersion: 'Stockfish 15.1',
      depth: 10,
      language: 'es',
      detailLevel: 'standard',
      retryable: false,
    });
    const res = await api.fetchAnalysisStatus(ANALYSIS_ID, f);
    assert.equal(res.kind, 'ok');
    assert.equal(res.status.status, 'processing');
  });

  test('404 = no encontrado', async () => {
    const f = fakeFetch(404);
    const res = await api.fetchAnalysisStatus(ANALYSIS_ID, f);
    assert.equal(res.kind, 'not_found');
  });
});

describe('resultado del análisis: GET /api/tutor/analyses/{id}/result', () => {
  const ANALYSIS_ID = '44444444-4444-4444-8444-444444444444';

  test('200 = devuelve informe completo con summary y explanation', async () => {
    const resultData = {
      analysisId: ANALYSIS_ID,
      gameId: '33333333-3333-4333-8333-333333333333',
      engineVersion: 'Stockfish 15.1',
      depth: 10,
      language: 'es',
      detailLevel: 'standard',
      explanation: 'Gran partida en la apertura...',
      summary: {
        white: { best: 10, good: 2, inaccuracy: 1, mistake: 0, blunder: 0, averageCpLoss: 12.5 },
        black: { best: 8, good: 3, inaccuracy: 2, mistake: 1, blunder: 0, averageCpLoss: 25.1 },
      },
      moves: [],
    };
    const f = fakeFetch(200, resultData);
    const res = await api.fetchAnalysisResult(ANALYSIS_ID, f);
    assert.equal(res.kind, 'ok');
    assert.equal(res.result.explanation, 'Gran partida en la apertura...');
  });

  test('409 = aún no listo', async () => {
    const f = fakeFetch(409);
    const res = await api.fetchAnalysisResult(ANALYSIS_ID, f);
    assert.equal(res.kind, 'not_ready');
  });
});

