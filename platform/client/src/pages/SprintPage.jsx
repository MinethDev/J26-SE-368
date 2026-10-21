// Sprint Intelligence page (owner: Wahalathanthri E. I.)
// Shows the latest sprint analysis for each active sprint: risk of missing the commitment with its SHAP
// drivers, the health score, the burndown, workload per person, recommendations and the sprint report.
import { useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ComponentPage from '../components/ComponentPage.jsx';
import ExplanationChart from '../components/ExplanationChart.jsx';
import { SeverityBadge } from '../components/Badge.jsx';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';

const SPRINT_TYPES = ['sprint-risk', 'sprint-health', 'sprint-burndown', 'sprint-workload', 'sprint-report'];
const REFRESH_SECONDS = 60;

// Plain-language names for the model features and health signals.
const FEATURE_NAMES = {
  delivered_so_far: 'Delivered so far',
  burndown_gap: 'Behind the burndown',
  health_score: 'Health score',
  committed_points: 'Points committed',
  committed_issues: 'Issues committed',
  planned_days: 'Sprint length (days)',
  elapsed_fraction: 'Share of sprint gone',
  scope_added: 'Work added mid-sprint',
  scope_removed: 'Work removed mid-sprint',
  unestimated: 'Unestimated issues',
  todo_share: 'Issues not started',
  in_progress_share: 'Issues in progress',
  late_work_not_started: 'Late work not started',
  team_prev_sprints: 'Team: earlier sprints',
  team_prev_delivered_mean: 'Team: past delivery',
  team_prev_missed_rate: 'Team: past misses',
};
const named = (items = []) => items.map((x) => ({ ...x, feature: FEATURE_NAMES[x.feature] || x.feature }));
const pct = (x) => `${Math.round(x * 100)}%`;

function groupBySprint(insights) {
  const sprints = new Map();
  for (const ins of insights) {
    if (!SPRINT_TYPES.includes(ins.type) || ins.target?.type !== 'sprint') continue;
    const s = sprints.get(ins.target.id) || { id: ins.target.id, name: ins.target.label || ins.target.id };
    s[ins.type.replace('sprint-', '')] = ins;
    sprints.set(ins.target.id, s);
  }
  return [...sprints.values()];
}

function RiskCard({ risk }) {
  if (!risk) return null;
  const p = risk.prediction.value;
  return (
    <div className="card sprint-tile">
      <div className="tile-head">
        <span className="section-label">Risk of missing the commitment</span>
        <SeverityBadge severity={risk.severity} />
      </div>
      <div className="stat-value">{pct(p)}</div>
      <p className="muted small">Chance the sprint delivers less than 80% of what it committed. Model {risk.modelVersion}.</p>
      <ExplanationChart items={named(risk.explanation)} upIsBad />
      <p className="muted small">Red bars push the risk up, green bars pull it down.</p>
    </div>
  );
}

function HealthCard({ health }) {
  if (!health) return null;
  return (
    <div className="card sprint-tile">
      <div className="tile-head">
        <span className="section-label">Sprint health</span>
        <SeverityBadge severity={health.severity} />
      </div>
      <div className="stat-value">{Math.round(health.prediction.value)}<span className="muted small"> / 100</span></div>
      <p className="muted small">Rule-based score: 100 minus the points each warning sign takes off.</p>
      <ExplanationChart items={named(health.explanation.filter((x) => x.impact !== 0))} />
    </div>
  );
}

function Burndown({ burndown }) {
  const rows = burndown?.prediction?.value || [];
  if (!rows.length) return null;
  const unit = burndown.prediction.unit;
  return (
    <div className="card">
      <div className="section-label">Burndown ({unit} of the commitment left)</div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="day" tickFormatter={(d) => `day ${d}`} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} width={40} />
          <Tooltip
            labelFormatter={(d) => `Day ${d}`}
            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="linear" dataKey="ideal" name="Ideal" stroke="var(--text-muted)" strokeDasharray="5 4" dot={false} />
          <Line type="linear" dataKey="remaining" name="Remaining" stroke="var(--accent)" strokeWidth={2} dot={false} />
          <Line type="linear" dataKey="scope" name="Total in sprint" stroke="var(--sev-medium)" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Recommendations({ risk }) {
  const recs = risk?.recommendations || [];
  if (!recs.length) return null;
  return (
    <div className="card">
      <div className="section-label">Recommended actions</div>
      <ol className="sprint-recs">
        {recs.map((r, i) => <li key={i}>{r}</li>)}
      </ol>
      <p className="muted small">Suggestions only: the team decides what to change.</p>
    </div>
  );
}

function Workload({ workload }) {
  const value = workload?.prediction?.value;
  if (!value?.people?.length) return null;
  const { unit, people, imbalance, unassignedOpenIssues } = value;
  return (
    <div className="card">
      <div className="tile-head">
        <span className="section-label">Workload per person ({unit})</span>
        <span className="muted small">imbalance {imbalance.toFixed(2)} (0 = even, 1 = one person has it all)</span>
      </div>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr><th>Person</th><th className="num">Open</th><th className="num">In progress</th><th className="num">Done</th><th>Share of open work</th></tr>
          </thead>
          <tbody>
            {people.map((p) => (
              <tr key={p.assignee}>
                <td>{p.assignee}</td>
                <td className="num">{p[`open_${unit}`]}</td>
                <td className="num">{p.in_progress}</td>
                <td className="num">{p[`done_${unit}`]}</td>
                <td>
                  <div className="share-bar"><span style={{ width: pct(p.share_of_open || 0) }} /></div>
                  <span className="muted small">{pct(p.share_of_open || 0)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unassignedOpenIssues > 0 && <p className="muted small">{unassignedOpenIssues} open issue(s) have no assignee.</p>}
      {workload.recommendations?.length > 0 && (
        <ul className="sprint-recs">{workload.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
      )}
    </div>
  );
}

// The report is simple Markdown (headings, lists, **bold**, _italic_); render just those.
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|_[^_]+_)/g).map((part, i) =>
    part.startsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong>
      : part.startsWith('_') && part.endsWith('_') && part.length > 2 ? <em key={i}>{part.slice(1, -1)}</em>
        : part);
}

function ReportText({ text }) {
  const blocks = [];
  for (const line of text.split('\n')) {
    const item = line.match(/^(\d+\.|-)\s+(.*)$/);
    const last = blocks[blocks.length - 1];
    if (item) {
      const kind = item[1] === '-' ? 'ul' : 'ol';
      if (last?.kind === kind) last.items.push(item[2]);
      else blocks.push({ kind, items: [item[2]] });
    } else if (line.startsWith('#')) blocks.push({ kind: 'h', text: line.replace(/^#+\s*/, '') });
    else if (line.trim()) blocks.push({ kind: 'p', text: line });
  }
  return (
    <div className="sprint-report">
      {blocks.map((b, i) => {
        if (b.kind === 'h') return <div key={i} className="section-label">{b.text}</div>;
        if (b.kind === 'p') return <p key={i}>{inline(b.text)}</p>;
        const List = b.kind;
        return <List key={i}>{b.items.map((x, j) => <li key={j}>{inline(x)}</li>)}</List>;
      })}
    </div>
  );
}

function Report({ report }) {
  if (!report) return null;
  return (
    <details className="card">
      <summary className="section-label">Sprint report ({report.prediction.label.replace(/^Sprint report \((.*)\)$/, '$1')})</summary>
      <ReportText text={report.prediction.value} />
    </details>
  );
}

function SprintAnalysis({ insights, loading, reload }) {
  const sprints = useMemo(() => groupBySprint(insights), [insights]);
  const [selected, setSelected] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(new Date());

  // Insights change whenever an analysis runs; re-read them every minute so the page stays current.
  useEffect(() => {
    const timer = setInterval(() => { reload(); setUpdatedAt(new Date()); }, REFRESH_SECONDS * 1000);
    return () => clearInterval(timer);
  }, [reload]);

  if (loading && !sprints.length) return null;
  if (!sprints.length) {
    return (
      <section>
        <h2>Active sprint</h2>
        <div className="card empty">No sprint analysis yet. Sync Jira on the Data sources page, then run the sprint analysis.</div>
      </section>
    );
  }
  const sprint = sprints.find((s) => s.id === selected) || sprints[0];

  return (
    <section>
      <div className="tile-head">
        <h2>{sprint.name}</h2>
        <div className="run-analysis">
          {sprints.length > 1 && (
            <select value={sprint.id} onChange={(e) => setSelected(e.target.value)}>
              {sprints.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          <span className="muted small">refreshed {updatedAt.toLocaleTimeString()}</span>
        </div>
      </div>
      <div className="sprint-grid">
        <RiskCard risk={sprint.risk} />
        <HealthCard health={sprint.health} />
      </div>
      <Burndown burndown={sprint.burndown} />
      <Recommendations risk={sprint.risk} />
      <Workload workload={sprint.workload} />
      <Report report={sprint.report} />
    </section>
  );
}

export default function SprintPage() {
  const { projectId } = useProject();
  const sprints = useApi(projectId ? `/projects/${encodeURIComponent(projectId)}/data/sprints` : null);
  const items = sprints.data?.items || [];

  return (
    <ComponentPage componentKey="sprint" hideTypes={SPRINT_TYPES}>
      {({ insights, loading, reload }) => (
        <>
          <SprintAnalysis insights={insights} loading={loading} reload={reload} />
          <section>
            <h2>Sprints</h2>
            {items.length === 0 ? (
              <div className="card empty">No sprints synced yet. Sync Jira on the Data sources page.</div>
            ) : (
              <table className="table">
                <thead><tr><th>Sprint</th><th>State</th><th>Start</th><th>End</th></tr></thead>
                <tbody>
                  {items.map((s) => (
                    <tr key={s._id}>
                      <td>{s.name}</td>
                      <td>{s.state}</td>
                      <td>{s.startDate ? new Date(s.startDate).toLocaleDateString() : '–'}</td>
                      <td>{s.endDate ? new Date(s.endDate).toLocaleDateString() : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </ComponentPage>
  );
}
