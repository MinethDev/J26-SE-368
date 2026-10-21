import ExplanationChart from './ExplanationChart.jsx';
import FeedbackButtons from './FeedbackButtons.jsx';
import { SeverityBadge, StubBadge } from './Badge.jsx';
import { componentByKey } from '../lib/components.js';
import { RISK_TYPES, breakablePath, evidenceHref, isDisclaimer } from '../lib/format.js';

function formatValue(value, unit) {
  if (value === null || value === undefined) return 'n/a';
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'none yet';
  if (typeof value === 'number') return `${Number.isInteger(value) ? value : value.toFixed(2)}${unit ? ` ${unit}` : ''}`;
  if (typeof value === 'object') return JSON.stringify(value);
  return `${value}${unit ? ` ${unit}` : ''}`;
}

// Shared widget: renders any insight in the common format (Contract 2).
// compact: hide the explanation chart (used where many cards sit side by side).
export default function InsightCard({ insight, showComponent = false, compact = false }) {
  const { title, type, prediction, confidence, explanation, recommendations = [], evidence = [], severity, isStub, modelVersion, component } = insight;
  const actions = recommendations.filter((r) => !isDisclaimer(r));
  const disclaimer = recommendations.find(isDisclaimer);

  return (
    <article className="card insight">
      <header className="insight-head">
        <div>
          {showComponent && <div className="eyebrow">{componentByKey[component]?.name || component}</div>}
          <h3>{breakablePath(title).map((p, i) => (typeof p === 'object' ? <wbr key={i} /> : p))}</h3>
        </div>
        <div className="badges">
          <SeverityBadge severity={severity} />
          {isStub && <StubBadge />}
        </div>
      </header>

      <div className="prediction">
        <span className="muted small">{prediction?.label}</span>
        <strong>{formatValue(prediction?.value, prediction?.unit)}</strong>
        {typeof confidence === 'number' && <span className="muted small">confidence {(confidence * 100).toFixed(0)}%</span>}
      </div>

      {!compact && <ExplanationChart items={explanation} upIsBad={RISK_TYPES.has(type)} legend />}

      {actions.length > 0 && (
        <div className="recommendations">
          <div className="section-label">What to do</div>
          <ul>
            {actions.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      <footer className="insight-foot">
        <details className="insight-details">
          <summary>Details</summary>
          {evidence.length > 0 && (
            <ul className="evidence-list">
              {evidence.map((e, i) => {
                const href = evidenceHref(e);
                return (
                  <li key={i}>
                    <span className="muted">{e.source}:</span>{' '}
                    {href ? <a href={href} target="_blank" rel="noreferrer">{e.ref}</a> : <span className="mono">{e.ref}</span>}
                    {e.note && <span className="muted"> ({e.note})</span>}
                  </li>
                );
              })}
            </ul>
          )}
          <div className="muted small">Model: {modelVersion}</div>
          {disclaimer && <div className="muted small">{disclaimer}</div>}
        </details>
        <FeedbackButtons insight={insight} />
      </footer>
    </article>
  );
}
