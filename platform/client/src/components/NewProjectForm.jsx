import { useState } from 'react';
import { api } from '../lib/api.js';
import { useProject } from '../lib/project.jsx';

// Lets a manager connect another project (e.g. a public GitHub repository) to DevIntel.
export default function NewProjectForm() {
  const { reload, setProjectId } = useProject();
  const [form, setForm] = useState({ key: '', name: '', owner: '', repo: '' });
  const [message, setMessage] = useState(null);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function create(e) {
    e.preventDefault();
    setMessage(null);
    try {
      await api('/projects', {
        method: 'POST',
        body: {
          key: form.key.trim(),
          name: form.name.trim(),
          github: { owner: form.owner.trim(), repo: form.repo.trim() },
        },
      });
      await reload();
      setProjectId(form.key.trim());
      setForm({ key: '', name: '', owner: '', repo: '' });
      setMessage({ kind: 'ok', text: 'Project created and selected. Sync GitHub above to bring in its data.' });
    } catch (err) {
      setMessage({ kind: 'error', text: err.message });
    }
  }

  return (
    <section>
      <h2>Connect another project</h2>
      <form className="card settings" onSubmit={create}>
        <div className="field-row">
          <div><label className="field-label" htmlFor="np-key">Project key (no spaces)</label><input id="np-key" value={form.key} onChange={set('key')} placeholder="azure-cli" required /></div>
          <div><label className="field-label" htmlFor="np-name">Project name</label><input id="np-name" value={form.name} onChange={set('name')} placeholder="Azure CLI (open source)" required /></div>
        </div>
        <div className="field-row">
          <div><label className="field-label" htmlFor="np-owner">GitHub owner</label><input id="np-owner" value={form.owner} onChange={set('owner')} placeholder="Azure" required /></div>
          <div><label className="field-label" htmlFor="np-repo">GitHub repository</label><input id="np-repo" value={form.repo} onChange={set('repo')} placeholder="azure-cli" required /></div>
        </div>
        <div className="run-analysis" style={{ marginTop: 12 }}>
          <button className="btn btn-primary" type="submit">Create project</button>
          {message && <span className={message.kind === 'error' ? 'error small' : 'muted small'}>{message.text}</span>}
        </div>
      </form>
    </section>
  );
}