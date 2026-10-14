import ExplanationChart from './ExplanationChart.jsx';
import FeedbackButtons from './FeedbackButtons.jsx';
import { SeverityBadge, StubBadge } from './Badge.jsx';

function formatValue(value, unit) {
  if (value === null || value === undefined) return 'n/a';
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'number') return `${Number.isInteger(value) ? value : value.toFixed(2)}${unit ? ` ${unit}` : ''}`;
  if (typeof value === 'object') return JSON.stringify(value);
  return `${value}${unit ? ` ${unit}` : ''}`;
}

// Shared widget: renders any insight in the common format (Contract 2).
export default function InsightCard({ insight, showComponent = false }) {
  const { title, prediction, confidence, explanation, recommendations, evidence, severity, isStub, modelVersion, component } = insight;
  return (
    <article className="card insight">
      <header className="insight-head">
        <h3>{title}</h3>
        <div className="badges">
          {showComponent && <span className="badge neutral">{component}</span>}
          <SeverityBadge severity={severity} />
          {isStub && <StubBadge />}
        </div>
      </header>

      <div className="prediction">
        <span className="muted">{prediction?.label}</span>
        <strong>{formatValue(prediction?.value, prediction?.unit)}</strong>
        {typeof confidence === 'number' && <span className="muted small">confidence {(confidence * 100).toFixed(0)}%</span>}
      </div>

      <ExplanationChart items={explanation} />

      {recommendations?.length > 0 && (
        <div className="recommendations">
          <div className="section-label">Recommendations</div>
          <ul>
            {recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {evidence?.length > 0 && (
        <div className="evidence muted small">
          Evidence: {evidence.map((e) => `${e.source}: ${e.ref}`).join(' · ')}
        </div>
      )}

      <footer className="insight-foot">
        <span className="muted small">model {modelVersion}</span>
        <FeedbackButtons insight={insight} />
      </footer>
    </article>
  );
}
