// Project Planning Intelligence page (owner: Vidusini W. M. O.)
// Add planning-specific views (plan timeline, resource table, etc.) inside <ComponentPage>.
import ComponentPage from '../components/ComponentPage.jsx';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';

export default function PlanningPage() {
  const { projectId } = useProject();
  const docs = useApi(projectId ? `/projects/${encodeURIComponent(projectId)}/data/requirements` : null);
  const items = docs.data?.items || [];

  return (
    <ComponentPage componentKey="planning">
      <section>
        <h2>Requirement documents</h2>
        {items.length === 0 ? (
          <div className="card empty">No documents uploaded yet. Upload an SRS on the Data sources page.</div>
        ) : (
          <table className="table">
            <thead><tr><th>File</th><th>Characters</th><th>Extracted requirements</th></tr></thead>
            <tbody>
              {items.map((d) => (
                <tr key={d._id}><td>{d.fileName}</td><td>{d.rawText?.length ?? 0}</td><td>{d.items?.length || 0}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </ComponentPage>
  );
}
