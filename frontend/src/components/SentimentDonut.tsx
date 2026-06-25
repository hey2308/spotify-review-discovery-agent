type SentimentDonutProps = {
  positive: number;
  neutral: number;
  negative: number;
};

type RingSegment = {
  value: number;
  color: string;
  label: string;
};

export default function SentimentDonut({ positive, neutral, negative }: SentimentDonutProps) {
  const total = positive + neutral + negative;
  const positivePct = total ? Math.round((positive / total) * 100) : 0;

  const cx = 110;
  const cy = 110;
  const radius = 74;
  const strokeWidth = 18;
  const circumference = 2 * Math.PI * radius;

  const segments: RingSegment[] = [
    { value: positive, color: "#1ed760", label: "Positive" },
    { value: neutral, color: "#5f6d78", label: "Neutral" },
    { value: negative, color: "#f2a6a6", label: "Negative" },
  ].filter((segment) => segment.value > 0);

  let offset = 0;
  const arcs = segments.map((segment) => {
    const length = total ? (segment.value / total) * circumference : 0;
    const arc = {
      ...segment,
      length,
      gap: circumference - length,
      offset: -offset,
    };
    offset += length;
    return arc;
  });

  return (
    <div className="sentiment-chart">
      <svg viewBox="0 0 220 220" className="sentiment-svg" aria-label="Sentiment distribution chart">
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          className="sentiment-track"
          strokeWidth={strokeWidth}
          fill="none"
        />

        {arcs.map((arc) => (
          <circle
            key={arc.label}
            cx={cx}
            cy={cy}
            r={radius}
            className="sentiment-arc"
            stroke={arc.color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            fill="none"
            strokeDasharray={`${arc.length} ${arc.gap}`}
            strokeDashoffset={arc.offset}
            transform={`rotate(-90 ${cx} ${cy})`}
          />
        ))}

        <text x={cx} y={96} textAnchor="middle" className="sentiment-overall">
          Overall
        </text>
        <text x={cx} y={124} textAnchor="middle" className="sentiment-value">
          {positivePct}%
        </text>
        <text x={cx} y={144} textAnchor="middle" className="sentiment-label">
          Positive
        </text>
      </svg>
    </div>
  );
}
