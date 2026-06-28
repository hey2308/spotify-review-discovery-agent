export type OverviewResponse = {
  pipeline_run_id: string | null;
  total_items: number;
  classified_items: number;
  date_range: { from: string; to: string };
  source_breakdown: Record<string, number>;
  sentiment_distribution: { positive: number; neutral: number; negative: number };
  headline_insight: string;
  counts: Record<string, number>;
};

export type ThemeSummary = {
  id: string;
  name: string;
  summary: string | null;
  mention_volume: number;
  sentiment_score: number | null;
  representative_quote_ids: string[];
};

export type ThemeDetail = ThemeSummary & {
  quotes: Array<{ id: string; text: string; source: string; sentiment_label: string | null }>;
  sub_patterns: Array<{ label: string; count: number }>;
};

export type QuestionsResponse = {
  items: Array<{
    question_id: string;
    question_text: string;
    answer_text: string;
    evidence_ids: string[];
    confidence: string | null;
    source_breakdown: Record<string, number> | null;
  }>;
  pipeline_run_id: string | null;
};

export type SegmentItem = {
  id: string;
  label: string;
  top_frustration: string | null;
  top_unmet_need: string | null;
  top_behavior: string | null;
};

export type UnmetNeedItem = {
  id: string;
  description: string;
  frequency: number;
  urgency_score: number | null;
  source_attribution: Record<string, number> | null;
};

export type QuoteItem = {
  id: string;
  text: string;
  source: string;
  rating: number | null;
  item_date: string;
  sentiment_label: string | null;
  sentiment_score: number | null;
  theme_ids: string[];
  theme_names: string[];
};

export type QuotesResponse = {
  items: QuoteItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

type QuoteQuery = {
  page?: number;
  page_size?: number;
  q?: string;
  source?: string;
  theme_id?: string;
  discovery_only?: boolean;
  rating_min?: number;
  rating_max?: number;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function apiOriginHint(): string {
  if (!API_BASE_URL) {
    return "Set VITE_API_BASE_URL on Vercel to your Render API URL and redeploy.";
  }
  return `Check that ${API_BASE_URL} is running and CORS_ORIGINS on Render includes this site.`;
}

async function apiFetch<T>(path: string): Promise<T> {
  if (!API_BASE_URL && import.meta.env.PROD) {
    throw new Error(`API URL is not configured. ${apiOriginHint()}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`);
  } catch {
    throw new Error(`Failed to fetch ${path}. ${apiOriginHint()}`);
  }

  if (!response.ok) {
    throw new Error(`Request failed (${response.status}): ${path}. ${apiOriginHint()}`);
  }
  return response.json() as Promise<T>;
}

function queryString(query: QuoteQuery): string {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === "" || value === null) return;
    params.set(key, String(value));
  });
  const q = params.toString();
  return q ? `?${q}` : "";
}

export function fetchOverview(): Promise<OverviewResponse> {
  return apiFetch<OverviewResponse>("/api/overview");
}

export async function fetchThemesWithDetails(): Promise<ThemeDetail[]> {
  const summaries = await apiFetch<{ items: ThemeSummary[] }>("/api/themes");
  const details = await Promise.all(
    summaries.items.map((theme) => apiFetch<ThemeDetail>(`/api/themes/${theme.id}`)),
  );
  return details;
}

export function fetchQuestions(): Promise<QuestionsResponse> {
  return apiFetch<QuestionsResponse>("/api/questions");
}

export function fetchSegments(): Promise<{ items: SegmentItem[]; pipeline_run_id: string | null }> {
  return apiFetch<{ items: SegmentItem[]; pipeline_run_id: string | null }>("/api/segments");
}

export function fetchUnmetNeeds(): Promise<{ items: UnmetNeedItem[]; pipeline_run_id: string | null }> {
  return apiFetch<{ items: UnmetNeedItem[]; pipeline_run_id: string | null }>("/api/unmet-needs");
}

export function fetchQuotes(query: QuoteQuery): Promise<QuotesResponse> {
  return apiFetch<QuotesResponse>(`/api/quotes${queryString(query)}`);
}
