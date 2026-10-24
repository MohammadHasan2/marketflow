
const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`API error ${response.status}: ${message}`);
  }

  return response.json() as Promise<T>;
}

export interface MarketPrice {
  symbol: string;
  trading_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source?: string;
  loaded_at: string;
}

export interface Overview {
  market: {
    tracked_symbols: number;
    price_records: number;
    latest_trading_date: string | null;
    last_loaded_at: string | null;
  };
  pipeline: {
    total_runs: number;
    successful_runs: number;
    failed_runs: number;
    last_run_at: string | null;
  };
  latest_prices: MarketPrice[];
}

export interface PipelineRun {
  run_id: string;
  dag_id: string;
  status: "running" | "success" | "failed";
  extracted_records: number;
  transformed_records: number;
  loaded_records: number;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
}

interface PageResponse<T> {
  data: T[];
  pagination: {
    page: number;
    page_size: number;
    total_records: number;
    total_pages: number;
  };
}

export const marketApi = {
  overview: () => request<Overview>("/api/overview"),

  prices: (page = 1, pageSize = 50) =>
    request<PageResponse<MarketPrice>>(
      `/api/prices?page=${page}&page_size=${pageSize}`
    ),

  history: (symbol: string, limit = 365) =>
    request<{ symbol: string; count: number; data: MarketPrice[] }>(
      `/api/prices/${encodeURIComponent(symbol)}/history?limit=${limit}`
    ),

  pipelineRuns: (page = 1, pageSize = 10) =>
    request<PageResponse<PipelineRun>>(
      `/api/pipeline-runs?page=${page}&page_size=${pageSize}`
    ),
};
