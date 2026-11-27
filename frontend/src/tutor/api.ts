import { apiUrl } from '../game/config';
import type { AnalysisResultData, AnalysisStatus } from './types';

export type RequestAnalysisResult =
  | { kind: 'ok'; status: AnalysisStatus; created: boolean }
  | { kind: 'unauthenticated' }
  | { kind: 'not_found'; message: string }
  | { kind: 'not_finished'; message: string }
  | { kind: 'not_analyzable'; message: string }
  | { kind: 'unavailable'; message: string };

export type StatusAnalysisResult =
  | { kind: 'ok'; status: AnalysisStatus }
  | { kind: 'unauthenticated' }
  | { kind: 'not_found' }
  | { kind: 'unavailable' };

export type ResultAnalysisResult =
  | { kind: 'ok'; result: AnalysisResultData }
  | { kind: 'not_ready' }
  | { kind: 'unauthenticated' }
  | { kind: 'not_found' }
  | { kind: 'unavailable' };

interface ErrorBody {
  error?: {
    code?: string;
    message?: string;
  };
}

/**
 * Solicita o reactiva un análisis de partida (sección 16.4.1).
 * POST /api/tutor/analyses -> 202 o 200 con AnalysisStatus.
 */
export async function requestAnalysis(
  gameId: string,
  options?: { language?: string; detailLevel?: string; depth?: number },
  fetchFn: typeof fetch = fetch
): Promise<RequestAnalysisResult> {
  try {
    const res = await fetchFn(apiUrl('/tutor/analyses'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        gameId,
        language: options?.language ?? 'es',
        detailLevel: options?.detailLevel ?? 'standard',
        ...(options?.depth ? { depth: options.depth } : {}),
      }),
    });

    if (res.status === 401) return { kind: 'unauthenticated' };

    const body = (await res.json().catch(() => null)) as (AnalysisStatus & ErrorBody) | null;
    const errorCode = body?.error?.code;
    const errorMessage = body?.error?.message ?? 'Error al solicitar el análisis.';

    if (res.status === 404) {
      return { kind: 'not_found', message: errorMessage };
    }

    if (res.status === 409) {
      if (errorCode === 'GAME_NOT_FINISHED') {
        return { kind: 'not_finished', message: errorMessage };
      }
      return { kind: 'not_analyzable', message: errorMessage };
    }

    if (!res.ok || !body || typeof body.analysisId !== 'string') {
      return { kind: 'unavailable', message: errorMessage };
    }

    return {
      kind: 'ok',
      status: body,
      created: res.status === 202,
    };
  } catch {
    return { kind: 'unavailable', message: 'No se pudo conectar con el servicio Tutor.' };
  }
}

/**
 * Consulta el estado de un análisis: pending, processing, completed o failed (sección 16.4).
 * GET /api/tutor/analyses/{id}
 */
export async function fetchAnalysisStatus(
  analysisId: string,
  fetchFn: typeof fetch = fetch
): Promise<StatusAnalysisResult> {
  try {
    const res = await fetchFn(apiUrl(`/tutor/analyses/${analysisId}`), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });

    if (res.status === 401) return { kind: 'unauthenticated' };
    if (res.status === 404) return { kind: 'not_found' };
    if (!res.ok) return { kind: 'unavailable' };

    const body = (await res.json().catch(() => null)) as AnalysisStatus | null;
    if (!body || typeof body.analysisId !== 'string') return { kind: 'unavailable' };

    return { kind: 'ok', status: body };
  } catch {
    return { kind: 'unavailable' };
  }
}

/**
 * Obtiene el informe final del análisis cuando status === 'completed' (sección 16.4.2).
 * GET /api/tutor/analyses/{id}/result
 */
export async function fetchAnalysisResult(
  analysisId: string,
  fetchFn: typeof fetch = fetch
): Promise<ResultAnalysisResult> {
  try {
    const res = await fetchFn(apiUrl(`/tutor/analyses/${analysisId}/result`), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });

    if (res.status === 401) return { kind: 'unauthenticated' };
    if (res.status === 404) return { kind: 'not_found' };
    if (res.status === 409) return { kind: 'not_ready' };
    if (!res.ok) return { kind: 'unavailable' };

    const body = (await res.json().catch(() => null)) as AnalysisResultData | null;
    if (!body || typeof body.analysisId !== 'string') return { kind: 'unavailable' };

    return { kind: 'ok', result: body };
  } catch {
    return { kind: 'unavailable' };
  }
}

