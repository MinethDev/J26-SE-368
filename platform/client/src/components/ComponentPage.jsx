import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';
import { componentByKey } from '../lib/components.js';
import InsightCard from './InsightCard.jsx';
import RunAnalysisButton from './RunAnalysisButton.jsx';

// Generic page for one intelligence component: header, run button, and its latest insights.
// Each component's own page file wraps this and can add component-specific views via `children`.
export default function ComponentPage({ componentKey, children }) {
  const meta = componentByKey[componentKey];
  const { projectId } = useProject();
  const { data, loading, error, reload } = useApi(projectId ? `/insights?projectId=${encodeURIComponent(projectId)}&component=${componentKey}` : null);
  const insights = data?.insights || [];

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{meta.name} Intelligence</h1>
          <p className="muted">{meta.summary}</p>
          <p className="muted small">Component owner: {meta.owner}</p>
        </div>
        <RunAnalysisButton projectId={projectId} components={[componentKey]} label={`Run ${meta.name.toLowerCase()} analysis`} onDone={reload} />
      </header>

      {children}

      <section>
        <h2>Latest insights</h2>
        {loading && <p className="muted">Loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && !error && insights.length === 0 && (
          <div className="card empty">No insights yet. Run the analysis to generate them.</div>
        )}
        <div className="insight-grid">
          {insights.map((ins) => (
            <InsightCard key={ins._id} insight={ins} />
          ))}
        </div>
      </section>
    </div>
  );
}
