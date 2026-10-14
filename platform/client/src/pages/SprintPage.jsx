// Sprint Intelligence page (owner: Wahalathanthri E. I.)
// Add sprint-specific views (burndown, workload per assignee, etc.) inside <ComponentPage>.
import ComponentPage from '../components/ComponentPage.jsx';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';

export default function SprintPage() {
  const { projectId } = useProject();
  const sprints = useApi(projectId ? `/projects/${encodeURIComponent(projectId)}/data/sprints` : null);
  const items = sprints.data?.items || [];

  return (
    <ComponentPage componentKey="sprint">
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
    </ComponentPage>
  );
}
