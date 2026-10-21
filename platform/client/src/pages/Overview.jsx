import { Link } from 'react-router-dom';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';
import { COMPONENTS, componentByKey } from '../lib/components.js';
import { isDisclaimer } from '../lib/format.js';
import RunAnalysisButton from '../components/RunAnalysisButton.jsx';
import { SeverityBadge, StatusPill } from '../components/Badge.jsx';

const SEVERITY_RANK = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };
const LEVELS = ['critical', 'high', 'medium', 'low'];
const bySeverity = (a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity];

function severityCounts(list) {
  const counts = Object.fromEntries(LEVELS.map((l) => [l, 0]));
  for (const i of list) if (i.severity in counts) counts[i.severity] += 1;
  return LEVELS.filter((l) => counts[l]).map((l) => ({ level: l, n: counts[l] }));
}

const firstAction = (ins) => (ins.recommendations || []).find((r) => !isDisclaimer(r));

export default function Overview() {
  const { project, projectId } = useProject();
  const q = projectId ? encodeURIComponent(projectId) : null;
  const summary = useApi(q ? `/projects/${q}/summary` : null);
  const health = useApi('/orchestrator/components/health');
  const runs = useApi(q ? `/orchestrator/runs?projectId=${q}` : null);
  const insights = useApi(q ? `/insights?projectId=${q}` : null);

  const reloadAll = () => {
    summary.reload();
    runs.reload();
    insights.reload();
    health.reload();
  };

  const counts = summary.data?.counts || {};
  const lastRun = runs.data?.runs?.[0];
  const all = insights.data?.insights || [];
  const attention = all.filter((i) => SEVERITY_RANK[i.severity] >= 2).sort(bySeverity).slice(0, 6);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{project?.name || 'Overview'}</h1>
          <p className="muted">Project health across planning, sprints, code quality and pull requests.</p>
        </div>
        <RunAnalysisButton projectId={projectId} onDone={reloadAll} />
      </header>

      <section className="stat-row">
        {[
          ['Pull requests', counts.pullRequests, `${counts.openPullRequests ?? 0} open`],
          ['Jira issues', counts.issues, `${counts.sprints ?? 0} sprints`],
          ['Quality files', counts.qualityFiles, 'from SonarQube'],
          ['Requirement docs', counts.requirements, 'uploaded'],
          ['Insights', counts.insights, 'in knowledge repository'],
        ].map(([label, value, sub]) => (
          <div className="card stat" key={label}>
            <div className="muted small">{label}</div>
            <div className="stat-value">{value ?? '–'}</div>
            <div className="muted small">{sub}</div>
          </div>
        ))}
      </section>

      <section>
        <h2>Intelligence components</h2>
        <div className="component-grid">
          {COMPONENTS.map((c, idx) => {
            const h = health.data?.components?.find((x) => x.component === c.key);
            const r = lastRun?.components?.find((x) => x.component === c.key);
            const mine = all.filter((i) => i.component === c.key);
            const top = [...mine].sort(bySeverity)[0];
            const sev = severityCounts(mine);
            return (
              <Link to={c.path} className="card component-card" key={c.key}>
                <div className="component-card-head">
                  <span className="step-no" aria-hidden="true">{idx + 1}</span>
                  <h3>{c.name}</h3>
                  <span className={`dot ${h?.up ? 'up' : 'down'}`} title={h?.up ? 'Service running' : `Service not running: ${h?.error || 'unknown'}`} />
                </div>
                <p className="muted small">{c.summary}</p>
                {top ? (
                  <div className="component-top">
                    <span className="muted small">Top item</span>
                    <span className="small">{top.title}</span>
                  </div>
                ) : (
                  <div className="muted small">No insights yet.</div>
                )}
                <div className="component-card-foot">
                  <span className="small">
                    {mine.length} insight{mine.length === 1 ? '' : 's'}
                    {sev.map(({ level, n }) => (
                      <span key={level} className={`count sev-${level}`}> · {n} {level}</span>
                    ))}
                  </span>
                  {r && <StatusPill status={r.status} />}
                </div>
              </Link>
            );
          })}
        </div>
        <p className="muted small flow-note">
          One analysis runs the components in order 1 → 4, and each one receives the insights produced before it
          (planning feeds sprint, quality feeds pull request).
          {lastRun && <> Last run {new Date(lastRun.startedAt).toLocaleString()} by {lastRun.triggeredBy}: {lastRun.status}.</>}
        </p>
      </section>

      <section>
        <h2>Needs attention</h2>
        {attention.length === 0 ? (
          <div className="card empty">{all.length ? 'Nothing above low severity right now.' : 'No insights yet. Run the analysis to generate them.'}</div>
        ) : (
          <ul className="attention-list">
            {attention.map((ins) => {
              const meta = componentByKey[ins.component];
              return (
                <li key={ins._id}>
                  <Link to={meta?.path || '/'} className="card attention-item">
                    <SeverityBadge severity={ins.severity} />
                    <div className="attention-body">
                      <div className="eyebrow">{meta?.name || ins.component}</div>
                      <div className="attention-title">{ins.title}</div>
                      {firstAction(ins) && <div className="muted small">{firstAction(ins)}</div>}
                    </div>
                    <span className="attention-go" aria-hidden="true">→</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
