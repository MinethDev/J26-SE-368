// Software Quality Intelligence page (owner: Senura Virantha S.J.)
// Add quality-specific views (hotspot map, debt trend, etc.) inside <ComponentPage>.
import ComponentPage from '../components/ComponentPage.jsx';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';

const COLUMNS = ['ncloc', 'complexity', 'bugs', 'vulnerabilities', 'code_smells', 'coverage'];
const COLUMN_NAMES = { ncloc: 'Lines of code', complexity: 'Complexity', bugs: 'Bugs', vulnerabilities: 'Vulnerabilities', code_smells: 'Code smells', coverage: 'Coverage %' };

export default function QualityPage() {
  const { projectId } = useProject();
  const files = useApi(projectId ? `/projects/${encodeURIComponent(projectId)}/data/quality` : null);
  const items = (files.data?.items || []).slice().sort((a, b) => (b.metrics?.complexity || 0) - (a.metrics?.complexity || 0)).slice(0, 15);

  return (
    <ComponentPage componentKey="quality">
      <section>
        <h2>Files by complexity</h2>
        {items.length === 0 ? (
          <div className="card empty">No SonarQube data synced yet. Sync SonarQube on the Data sources page.</div>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead><tr><th>File</th>{COLUMNS.map((c) => <th key={c} className="num">{COLUMN_NAMES[c]}</th>)}</tr></thead>
              <tbody>
                {items.map((f) => (
                  <tr key={f._id}>
                    <td className="mono">{f.path}</td>
                    {COLUMNS.map((c) => <td key={c} className="num">{f.metrics?.[c] ?? '–'}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </ComponentPage>
  );
}
