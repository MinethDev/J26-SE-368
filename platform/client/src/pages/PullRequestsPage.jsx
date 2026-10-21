// Pull Request Intelligence page (owner: Perera W. M. M.)
// Unified PR view: one row per open PR with the three results at a glance (merge readiness, recommended
// reviewers, AI code review). Selecting a PR shows its three insight cards side by side.
import { useEffect, useMemo, useState } from 'react';
import ComponentPage from '../components/ComponentPage.jsx';
import InsightCard from '../components/InsightCard.jsx';
import { SeverityBadge } from '../components/Badge.jsx';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';

const PR_TYPES = ['merge-readiness', 'reviewer-recommendation', 'code-review'];
const SEVERITY_RANK = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };

function readinessText(value) {
  if (!value) return '–';
  if (/^no blocking/i.test(value)) return 'No blocking issues';
  if (/^insufficient/i.test(value)) return 'Not enough information';
  return value;
}

function findingCount(insight) {
  const m = String(insight?.prediction?.value ?? '').match(/\d+/);
  return m ? Number(m[0]) : null;
}

const touchesHotspot = (readiness) => (readiness?.recommendations || []).some((r) => /^touches quality hotspot/i.test(r));

// Insights grouped by PR number: { '9': { 'merge-readiness': …, 'reviewer-recommendation': …, 'code-review': … } }
function groupByPr(insights) {
  const out = {};
  for (const ins of insights) {
    if (!PR_TYPES.includes(ins.type) || ins.target?.type !== 'pullRequest') continue;
    (out[ins.target.id] ||= {})[ins.type] = ins;
  }
  return out;
}

function PrTable({ prs, byPr, selected, onSelect }) {
  return (
    <div className="table-scroll">
      <table className="table pr-table">
        <thead>
          <tr>
            <th>Pull request</th>
            <th>Merge readiness</th>
            <th>Suggested reviewers</th>
            <th className="num">AI findings</th>
          </tr>
        </thead>
        <tbody>
          {prs.map((p) => {
            const g = byPr[String(p.number)] || {};
            const ready = g['merge-readiness'];
            const reviewers = g['reviewer-recommendation']?.prediction?.value;
            const findings = findingCount(g['code-review']);
            const isSel = String(p.number) === selected;
            return (
              <tr key={p._id} className={`clickable${isSel ? ' selected' : ''}`} onClick={() => onSelect(String(p.number))} tabIndex={0}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(String(p.number))} aria-selected={isSel}>
                <td>
                  <div className="pr-title">#{p.number} {p.title}</div>
                  <div className="muted small">
                    {p.author} · {p.files?.length ?? 0} file{p.files?.length === 1 ? '' : 's'} · +{p.additions ?? 0} / −{p.deletions ?? 0}
                    {touchesHotspot(ready) && <span className="chip warn">touches a quality hotspot</span>}
                  </div>
                </td>
                <td>{ready ? <span className={`readiness sev-${ready.severity}`}>{readinessText(ready.prediction?.value)}</span> : <span className="muted">not analysed</span>}</td>
                <td>{Array.isArray(reviewers) && reviewers.length ? reviewers.slice(0, 3).join(', ') : <span className="muted">no history yet</span>}</td>
                <td className="num">{findings ?? '–'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PrDetail({ pr, group }) {
  if (!pr) return null;
  const cards = PR_TYPES.map((t) => group?.[t]).filter(Boolean);
  const ready = group?.['merge-readiness'];
  return (
    <section className="pr-detail">
      <div className="pr-detail-head">
        <div>
          <h2>
            #{pr.number} {pr.title}
          </h2>
          <p className="muted small">
            by {pr.author} · {pr.reviews?.length ? `reviews: ${pr.reviews.map((r) => `${r.reviewer} (${r.state.toLowerCase()})`).join(', ')}` : 'no reviews yet'}
            {pr.url && (
              <>
                {' · '}
                <a href={pr.url} target="_blank" rel="noreferrer">open on GitHub</a>
              </>
            )}
          </p>
        </div>
        {ready && <SeverityBadge severity={ready.severity} />}
      </div>
      {pr.files?.length > 0 && (
        <p className="small file-list">
          <span className="muted">Changed files: </span>
          {pr.files.map((f) => <code key={f.path}>{f.path}</code>)}
        </p>
      )}
      {cards.length === 0 ? (
        <div className="card empty">No analysis for this pull request yet. Run the analysis above.</div>
      ) : (
        <div className="pr-cards">
          {cards.map((ins) => <InsightCard key={ins._id} insight={ins} />)}
        </div>
      )}
    </section>
  );
}

function UnifiedView({ insights, loading }) {
  const { projectId } = useProject();
  const prsApi = useApi(projectId ? `/projects/${encodeURIComponent(projectId)}/data/pull-requests` : null);
  const byPr = useMemo(() => groupByPr(insights), [insights]);
  const prs = useMemo(() => {
    const open = (prsApi.data?.items || []).filter((p) => p.state === 'open');
    const rank = (p) => SEVERITY_RANK[byPr[String(p.number)]?.['merge-readiness']?.severity] ?? -1;
    return open.sort((a, b) => rank(b) - rank(a) || b.number - a.number);
  }, [prsApi.data, byPr]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (prs.length && !prs.some((p) => String(p.number) === selected)) setSelected(String(prs[0].number));
  }, [prs, selected]);

  if (prsApi.loading || loading) return <p className="muted">Loading…</p>;
  if (!prs.length) return <div className="card empty">No open pull requests. Sync GitHub on the Data sources page.</div>;

  return (
    <>
      <section>
        <h2>Open pull requests</h2>
        <p className="muted small">Select a pull request to see its reviewers, merge readiness and AI code review together.</p>
        <PrTable prs={prs} byPr={byPr} selected={selected} onSelect={setSelected} />
      </section>
      <PrDetail pr={prs.find((p) => String(p.number) === selected)} group={byPr[selected]} />
    </>
  );
}

export default function PullRequestsPage() {
  return (
    <ComponentPage componentKey="pull-request" hideTypes={PR_TYPES}>
      {({ insights, loading }) => <UnifiedView insights={insights} loading={loading} />}
    </ComponentPage>
  );
}
