import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import * as api from "../src/api/client";

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders dashboard sections from API data", async () => {
    vi.spyOn(api, "fetchOverview").mockResolvedValue({
      pipeline_run_id: "run-1",
      total_items: 120,
      classified_items: 100,
      date_range: { from: "2026-01-01", to: "2026-02-01" },
      source_breakdown: { social: 80, play_store: 40 },
      sentiment_distribution: { positive: 70, neutral: 20, negative: 10 },
      headline_insight: "Largest theme is Algorithmic Discovery Issues.",
      counts: { feedback_items: 120, analyses: 100, themes: 2, answers: 6, segments: 2, unmet_needs: 2 },
    });
    vi.spyOn(api, "fetchThemesWithDetails").mockResolvedValue([
      {
        id: "theme-1",
        name: "Algorithmic Music Discovery Issues",
        summary: "Users feel stuck in stale recommendations.",
        mention_volume: 60,
        sentiment_score: 0.43,
        representative_quote_ids: [],
        quotes: [],
        sub_patterns: [],
      },
      {
        id: "theme-2",
        name: "Shuffle Play Frustration",
        summary: "Shuffle repeats the same songs.",
        mention_volume: 40,
        sentiment_score: 0.31,
        representative_quote_ids: [],
        quotes: [],
        sub_patterns: [],
      },
    ]);
    vi.spyOn(api, "fetchQuestions").mockResolvedValue({
      pipeline_run_id: "run-1",
      items: [
        {
          question_id: "Q1",
          question_text: "Why do users struggle to discover new music?",
          answer_text: "Algorithms over-index on old listening history.",
          evidence_ids: ["a", "b", "c"],
          confidence: "high",
          source_breakdown: { social: 3 },
        },
      ],
    });
    vi.spyOn(api, "fetchSegments").mockResolvedValue({
      pipeline_run_id: "run-1",
      items: [
        {
          id: "seg-1",
          label: "Power Listeners",
          top_frustration: "Stale recommendations",
          top_unmet_need: "Underground discovery",
          top_behavior: "Uses external blogs",
        },
      ],
    });
    vi.spyOn(api, "fetchUnmetNeeds").mockResolvedValue({
      pipeline_run_id: "run-1",
      items: [
        {
          id: "need-1",
          description: "More control over recommendation taste",
          frequency: 8,
          urgency_score: 0.81,
          source_attribution: { social: 5, play_store: 3 },
        },
      ],
    });
    vi.spyOn(api, "fetchQuotes").mockResolvedValue({
      items: [
        {
          id: "quote-1",
          text: "Discover Weekly is stale.",
          source: "social",
          rating: null,
          item_date: "2026-01-10T00:00:00Z",
          sentiment_label: "negative",
          sentiment_score: 0.2,
          theme_ids: ["theme-1"],
          theme_names: ["Algorithmic Music Discovery Issues"],
        },
      ],
      page: 1,
      page_size: 25,
      total: 1,
      total_pages: 1,
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: /Spotify Music Discovery Intelligence/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Theme Clusters/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /AI Q&A Intelligence/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Verbatim Quote Explorer/i })).toBeInTheDocument();
    expect(screen.getByText(/Power Listeners/i)).toBeInTheDocument();
    expect(screen.getByText(/3 Months/i)).toBeInTheDocument();
  });
});
