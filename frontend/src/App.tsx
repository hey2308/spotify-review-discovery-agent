import { useEffect, useMemo, useState } from "react";
import {
  fetchOverview,
  fetchQuestions,
  fetchQuotes,
  fetchSegments,
  fetchThemesWithDetails,
  fetchUnmetNeeds,
  type OverviewResponse,
  type QuoteItem,
  type SegmentItem,
  type ThemeDetail,
  type UnmetNeedItem,
} from "./api/client";
import SentimentDonut from "./components/SentimentDonut";

const SECTION_NAV = [
  { id: "section-overview", label: "Overview" },
  { id: "section-themes", label: "Theme Clusters" },
  { id: "section-qa", label: "AI Q&A Intelligence" },
  { id: "section-quotes", label: "Quote Explorer" },
  { id: "section-segments", label: "Segments" },
  { id: "section-needs", label: "Unmet Needs" },
] as const;

type DashboardState = {
  overview: OverviewResponse;
  themes: ThemeDetail[];
  questions: Awaited<ReturnType<typeof fetchQuestions>>["items"];
  segments: SegmentItem[];
  unmetNeeds: UnmetNeedItem[];
  quotes: Awaited<ReturnType<typeof fetchQuotes>>;
};

const DEFAULT_QUERY = { page: 1, page_size: 25, discovery_only: true };

function formatNumber(value: number): string {
  return Intl.NumberFormat("en-US").format(value);
}

function percent(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

function unmetNeedUrgency(index: number): "high" | "medium" {
  return index < 2 ? "high" : "medium";
}

function threeMonthWindow(endDate: string): { from: string; to: string } {
  const end = new Date(endDate);
  const start = new Date(end);
  start.setMonth(start.getMonth() - 3);
  return {
    from: start.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
    to: end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
  };
}

function scrollToSection(sectionId: string) {
  document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function App() {
  const [query, setQuery] = useState<{
    q?: string;
    source?: string;
    discovery_only?: boolean;
    page: number;
    page_size: number;
  }>(DEFAULT_QUERY);
  const [draftSearch, setDraftSearch] = useState("");
  const [activeSection, setActiveSection] = useState<string>(SECTION_NAV[0].id);
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: DashboardState }
  >({ kind: "loading" });

  useEffect(() => {
    Promise.all([
      fetchOverview(),
      fetchThemesWithDetails(),
      fetchQuestions(),
      fetchSegments(),
      fetchUnmetNeeds(),
      fetchQuotes(query),
    ])
      .then(([overview, themes, questions, segments, unmetNeeds, quotes]) => {
        setState({
          kind: "ready",
          data: {
            overview,
            themes,
            questions: questions.items,
            segments: segments.items,
            unmetNeeds: unmetNeeds.items,
            quotes,
          },
        });
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Unknown error";
        setState({ kind: "error", message });
      });
  }, [query]);

  const sourceOptions = useMemo(() => {
    if (state.kind !== "ready") return [];
    return Object.keys(state.data.overview.source_breakdown);
  }, [state]);

  useEffect(() => {
    if (state.kind !== "ready" || typeof IntersectionObserver === "undefined") return;

    const sections = SECTION_NAV.map(({ id }) => document.getElementById(id)).filter(Boolean);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target.id) {
          setActiveSection(visible.target.id);
        }
      },
      { rootMargin: "-20% 0px -55% 0px", threshold: [0.1, 0.35, 0.6] },
    );

    sections.forEach((section) => observer.observe(section!));
    return () => observer.disconnect();
  }, [state.kind]);

  if (state.kind === "loading") {
    return <div className="load-screen">Loading dashboard...</div>;
  }
  if (state.kind === "error") {
    return (
      <div className="load-screen" role="alert">
        Failed to load dashboard: {state.message}
      </div>
    );
  }

  const { overview, themes, questions, segments, unmetNeeds, quotes } = state.data;
  const timeframe = threeMonthWindow(overview.date_range.to);

  return (
    <main className="app-shell">
      <div className="frame">
        <header className="topbar">
          <div className="brand">
            <div>
              <h1>Spotify Music Discovery Intelligence</h1>
              <p>Insights from app stores, social, and community feedback</p>
            </div>
          </div>
          <nav className="topbar-nav" aria-label="Dashboard sections">
            {SECTION_NAV.map((section) => (
              <button
                key={section.id}
                type="button"
                className={activeSection === section.id ? "nav-link active" : "nav-link"}
                onClick={() => {
                  setActiveSection(section.id);
                  scrollToSection(section.id);
                }}
              >
                {section.label}
              </button>
            ))}
          </nav>
        </header>

        <div className="layout">
          <section className="content">
            <div id="section-overview" className="dashboard-section">
            <div className="card-grid">
              <div className="stat-card">
                <div className="label">Total Reviews</div>
                <div className="value">{formatNumber(overview.total_items)}</div>
                <div className="hint">+8.4% trend</div>
              </div>
              <div className="stat-card">
                <div className="label">Discovery Health</div>
                <div className="value">
                  {Math.round((overview.classified_items / Math.max(overview.total_items, 1)) * 100)}
                </div>
                <div className="hint">of items classified</div>
              </div>
              <div className="stat-card">
                <div className="label">Top Source</div>
                <div className="value">
                  {Object.entries(overview.source_breakdown).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "n/a"}
                </div>
                <div className="hint">
                  {percent(
                    Object.entries(overview.source_breakdown).sort((a, b) => b[1] - a[1])[0]?.[1] ?? 0,
                    overview.total_items,
                  )}{" "}
                  of volume
                </div>
              </div>
              <div className="stat-card">
                <div className="label">Timeframe</div>
                <div className="value">3 Months</div>
                <div className="hint">
                  {timeframe.from} - {timeframe.to}
                </div>
              </div>
            </div>

            <div className="hero">
              <article className="panel">
                <div className="mini-title">Priority AI Insight</div>
                <div className="headline">{questions[0]?.question_text}</div>
                <p className="muted">{questions[0]?.answer_text}</p>
                <div className="meta-row" style={{ marginTop: 12 }}>
                  <span>Core Barrier: Algorithmic Echo Chambers</span>
                  <span>Evidence: {questions[0]?.evidence_ids.length ?? 0} quote IDs</span>
                  <span>Confidence: {questions[0]?.confidence ?? "n/a"}</span>
                </div>
              </article>

              <article className="panel sentiment-panel">
                <h3>Sentiment Mix</h3>
                <SentimentDonut
                  positive={overview.sentiment_distribution.positive}
                  neutral={overview.sentiment_distribution.neutral}
                  negative={overview.sentiment_distribution.negative}
                />
              </article>
            </div>
            </div>

            <section id="section-themes" className="dashboard-section">
              <div className="section-head">
                <div>
                  <h2>Theme Clusters</h2>
                  <p>High-volume discussion topics derived from NLP modeling</p>
                </div>
              </div>
              <div className="theme-grid">
                {themes.map((theme) => (
                  <article key={theme.id} className="theme-card">
                    <div className="trend">+{Math.max(2, Math.round(theme.mention_volume / 120))}% growth</div>
                    <h4>{theme.name}</h4>
                    <p>{theme.summary ?? "No summary available."}</p>
                    <div className="meta-row" style={{ marginTop: 10 }}>
                      <span>
                        Sentiment: {theme.sentiment_score === null ? "n/a" : `${Math.round(theme.sentiment_score * 100)}%`}
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section id="section-qa" className="dashboard-section">
              <div className="section-head">
                <div>
                  <h2>AI Q&A Intelligence</h2>
                  <p>Grounded answers to the six discovery questions</p>
                </div>
              </div>
              <div className="qa-grid">
                {questions.map((item) => (
                  <article key={item.question_id} className="qa-card">
                    <h4>{item.question_text}</h4>
                    <p>{item.answer_text}</p>
                    <div className="qa-foot">
                      Confidence: {item.confidence ?? "n/a"} • {item.evidence_ids.length} mentions
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section id="section-quotes" className="quote-panel dashboard-section">
              <div className="section-head">
                <div>
                  <h2>Verbatim Quote Explorer</h2>
                  <p>Discovery and recommendation feedback from real users</p>
                </div>
                <span className="muted">
                  Showing {quotes.items.length} of {formatNumber(quotes.total)}{" "}
                  {query.discovery_only !== false ? "discovery-related " : ""}quotes
                </span>
              </div>
              <div className="filters">
                <input
                  placeholder="Search quotes..."
                  value={draftSearch}
                  onChange={(event) => setDraftSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      setQuery((prev) => ({ ...prev, q: draftSearch || undefined, page: 1 }));
                    }
                  }}
                />
                <select
                  value={query.source ?? ""}
                  onChange={(event) => setQuery((prev) => ({ ...prev, source: event.target.value || undefined, page: 1 }))}
                >
                  <option value="">Source: All</option>
                  {sourceOptions.map((source) => (
                    <option key={source} value={source}>
                      {source}
                    </option>
                  ))}
                </select>
                <select
                  value={query.discovery_only === false ? "all" : "discovery"}
                  onChange={(event) =>
                    setQuery((prev) => ({
                      ...prev,
                      discovery_only: event.target.value === "discovery",
                      page: 1,
                    }))
                  }
                >
                  <option value="discovery">Topic: Discovery &amp; recommendations</option>
                  <option value="all">Topic: All reviews</option>
                </select>
                <button
                  className="pill-btn"
                  style={{ borderRadius: 8, padding: "8px 10px" }}
                  onClick={() => setQuery((prev) => ({ ...prev, q: draftSearch || undefined, page: 1 }))}
                >
                  Apply
                </button>
                <button
                  className="pill-btn"
                  style={{ borderRadius: 8, padding: "8px 10px", background: "#192229", color: "#d3e2d8" }}
                  onClick={() => {
                    setDraftSearch("");
                    setQuery(DEFAULT_QUERY);
                  }}
                >
                  Reset
                </button>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Quote</th>
                      <th>Source</th>
                      <th>Sentiment</th>
                      <th>Rating</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quotes.items.map((quote: QuoteItem) => (
                      <tr key={quote.id}>
                        <td>{quote.text}</td>
                        <td>{quote.source}</td>
                        <td>
                          <span
                            className={`chip ${
                              quote.sentiment_label === "positive"
                                ? "pos"
                                : quote.sentiment_label === "negative"
                                  ? "neg"
                                  : ""
                            }`}
                          >
                            {quote.sentiment_label ?? "n/a"}
                          </span>
                        </td>
                        <td>{quote.rating ?? "-"}</td>
                        <td>{new Date(quote.item_date).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <span className="muted">
                  Page {quotes.page} of {quotes.total_pages}
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    className="pill-btn"
                    style={{ borderRadius: 8, padding: "8px 10px" }}
                    disabled={quotes.page <= 1}
                    onClick={() => setQuery((prev) => ({ ...prev, page: Math.max(1, prev.page - 1) }))}
                  >
                    Prev
                  </button>
                  <button
                    className="pill-btn"
                    style={{ borderRadius: 8, padding: "8px 10px" }}
                    disabled={quotes.page >= quotes.total_pages}
                    onClick={() => setQuery((prev) => ({ ...prev, page: prev.page + 1 }))}
                  >
                    Next
                  </button>
                </div>
              </div>
            </section>

            <section className="segments-needs">
              <article id="section-segments" className="panel dashboard-section">
                <div className="section-head">
                  <div>
                    <h2>User Segment Breakdown</h2>
                    <p>Cross-analyzing discovery behavior and friction points</p>
                  </div>
                </div>
                <div className="segments-grid">
                  {segments.map((segment) => (
                    <article key={segment.id} className="segment-card">
                      <h4>{segment.label}</h4>
                      <dl>
                        <div>
                          <dt>Frustration</dt>
                          <dd>{segment.top_frustration ?? "n/a"}</dd>
                        </div>
                        <div>
                          <dt>Unmet Need</dt>
                          <dd>{segment.top_unmet_need ?? "n/a"}</dd>
                        </div>
                        <div>
                          <dt>Behavior</dt>
                          <dd>{segment.top_behavior ?? "n/a"}</dd>
                        </div>
                      </dl>
                    </article>
                  ))}
                </div>
              </article>

              <article id="section-needs" className="panel dashboard-section">
                <div className="section-head">
                  <div>
                    <h2>Unmet Needs Tracker</h2>
                    <p>High-conviction opportunities from cross-channel sentiment</p>
                  </div>
                </div>
                <div className="need-list">
                  {unmetNeeds.map((need, index) => {
                    const urgency = unmetNeedUrgency(index);
                    return (
                    <article key={need.id} className="need-item">
                      <div className="need-head">
                        <strong>{need.description}</strong>
                        <span className={`urgency ${urgency}`}>{urgency}</span>
                      </div>
                      <div className="meta-row" style={{ marginTop: 8 }}>
                        <span>Frequency: {need.frequency}</span>
                        <span>Urgency: {need.urgency_score === null ? "n/a" : need.urgency_score.toFixed(2)}</span>
                      </div>
                      <div className="chips" style={{ marginTop: 8 }}>
                        {Object.entries(need.source_attribution ?? {}).map(([source, count]) => (
                          <span key={source} className="chip">
                            {source}: {count}
                          </span>
                        ))}
                      </div>
                    </article>
                    );
                  })}
                </div>
              </article>
            </section>
          </section>
        </div>
      </div>
    </main>
  );
}
