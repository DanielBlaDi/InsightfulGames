// Tipos de Tutor y Análisis de partidas (contrato técnico definitivo, sección 16.4).

export type AnalysisStatusValue = 'pending' | 'processing' | 'completed' | 'failed';

export interface AnalysisStatus {
  analysisId: string;
  gameId: string;
  status: AnalysisStatusValue;
  engineVersion: string;
  depth: number;
  language: string;
  detailLevel: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  error?: string | null;
  retryable: boolean;
}

export interface MoveScoreSummary {
  best: number;
  good: number;
  inaccuracy: number;
  mistake: number;
  blunder: number;
  averageCpLoss: number;
}

export interface BestMoveData {
  uci?: string;
  san?: string;
}

export interface AnalysisMoveItem {
  ply: number;
  color: 'white' | 'black';
  uci: string;
  san: string;
  bestMove?: BestMoveData;
  evalBefore?: number | null;
  evalAfter?: number | null;
  cpLoss?: number | null;
  classification?: 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder' | 'book' | string;
}

export interface AnalysisResultData {
  analysisId: string;
  gameId: string;
  engineVersion: string;
  depth: number;
  language: string;
  detailLevel: string;
  summary?: {
    white: MoveScoreSummary;
    black: MoveScoreSummary;
  };
  moves?: AnalysisMoveItem[];
  explanation: string;
  createdAt?: string;
}

