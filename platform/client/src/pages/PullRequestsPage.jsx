// Pull Request Intelligence page (owner: Perera W. M. M.)
// Add PR-specific views (summary, reviewer ranking, review findings) inside <ComponentPage>.
import ComponentPage from '../components/ComponentPage.jsx';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';

export default function PullRequestsPage() {
  const { projectId } = useProject();
  const prs = useApi(projectId ? `/projects/${encodeURIComponent(projectId)}/data/pull-requests` : null);
  const open = (prs.data?.items || []).filter((p) => p.state === 'open');

  return (
    <ComponentPage componentKey="pull-request">
      <section>
        <h2>Open pull requests</h2>
        {open.length === 0 ? (
          <div className="card empty">No open pull requests. Sync GitHub on the Data sources page.</div>
        ) : (
          <table className="table">
            <thead><tr><th>#</th><th>Title</th><th>Author</th><th className="num">Files</th><th className="num">+/−</th><th>Reviews</th></tr></thead>
            <tbody>
              {open.map((p) => (
                <tr key={p._id}>
                  <td>{p.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.number}</a> : p.number}</td>
                  <td>{p.title}</td>
                  <td>{p.author}</td>
                  <td className="num">{p.changedFiles ?? p.files?.length ?? '–'}</td>
                  <td className="num">+{p.additions ?? 0} / −{p.deletions ?? 0}</td>
                  <td>{p.reviews?.length ? p.reviews.map((r) => `${r.reviewer} (${r.state.toLowerCase()})`).join(', ') : 'none'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </ComponentPage>
  );
}
