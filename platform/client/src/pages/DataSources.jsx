import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { useProject } from '../lib/project.jsx';
import NewProjectForm from '../components/NewProjectForm.jsx';

const SOURCES = [
  { key: 'github', name: 'GitHub', desc: 'Repository, pull requests, changed files and reviews' },
  { key: 'jira', name: 'Jira', desc: 'Sprints and issues from a Scrum board' },
  { key: 'sonarqube', name: 'SonarQube', desc: 'File-level quality metrics and open issues' },
];

function SyncCard({ source, project, onSynced, canEdit }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const last = project?.lastSync?.[source.key];

  async function sync() {
    setBusy(true);
    setMessage(null);
    try {
      const d = await api(`/projects/${encodeURIComponent(project.key)}/sync/${source.key}`, { method: 'POST', body: {} });
      setMessage({ kind: 'ok', text: Object.entries(d.result).map(([k, v]) => `${k}: ${v}`).join(', ') });
      onSynced();
    } catch (e) {
      setMessage({ kind: 'error', text: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card source">
      <h3>{source.name}</h3>
      <p className="muted small">{source.desc}</p>
      <p className="small">Last sync: {last ? new Date(last).toLocaleString() : 'never'}</p>
      {canEdit && <button className="btn" onClick={sync} disabled={busy}>{busy ? 'Syncing…' : `Sync ${source.name}`}</button>}
      {message && <p className={message.kind === 'error' ? 'error small' : 'muted small'}>{message.text}</p>}
    </div>
  );
}

export default function DataSources() {
  const { isManager } = useAuth();
  const { project, reload } = useProject();
  const [form, setForm] = useState({ owner: '', repo: '', boardId: '', projectKey: '' });
  const [saved, setSaved] = useState(null);
  const [upload, setUpload] = useState(null);

  useEffect(() => {
    if (!project) return;
    setForm({
      owner: project.github?.owner || '',
      repo: project.github?.repo || '',
      boardId: project.jira?.boardId ?? '',
      projectKey: project.sonarqube?.projectKey || '',
    });
  }, [project]);

  if (!project) return <div className="page"><p className="muted">Loading project…</p></div>;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save(e) {
    e.preventDefault();
    setSaved(null);
    try {
      await api(`/projects/${encodeURIComponent(project.key)}`, {
        method: 'PATCH',
        body: {
          github: { owner: form.owner.trim(), repo: form.repo.trim() },
          jira: { boardId: form.boardId === '' ? null : Number(form.boardId) },
          sonarqube: { projectKey: form.projectKey.trim() },
        },
      });
      setSaved({ kind: 'ok', text: 'Saved.' });
      reload();
    } catch (err) {
      setSaved({ kind: 'error', text: err.message });
    }
  }

  async function uploadFile(e) {
    e.preventDefault();
    const file = e.target.elements.file.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    setUpload(null);
    try {
      const d = await api(`/projects/${encodeURIComponent(project.key)}/requirements`, { method: 'POST', form: fd });
      setUpload({ kind: 'ok', text: `Uploaded ${d.fileName} (${d.characters} characters extracted).` });
      e.target.reset();
      reload();
    } catch (err) {
      setUpload({ kind: 'error', text: err.message });
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Data sources</h1>
          <p className="muted">Data Integration Layer: connect the project's tools and bring their data into DevIntel.</p>
        </div>
      </header>

      <section className="source-grid">
        {SOURCES.map((s) => (
          <SyncCard key={s.key} source={s} project={project} onSynced={reload} canEdit={isManager} />
        ))}
        <div className="card source">
          <h3>Requirement documents</h3>
          <p className="muted small">Upload an SRS/BRD (.pdf, .txt or .md) for Planning Intelligence</p>
          {isManager ? (
            <form onSubmit={uploadFile} className="upload-form">
              <input type="file" name="file" accept=".pdf,.txt,.md" />
              <button className="btn" type="submit">Upload</button>
            </form>
          ) : (
            <p className="muted small">Managers can upload documents.</p>
          )}
          {upload && <p className={upload.kind === 'error' ? 'error small' : 'muted small'}>{upload.text}</p>}
        </div>
      </section>

      {isManager && (
        <section>
          <h2>Project settings</h2>
          <form className="card settings" onSubmit={save}>
            <div className="field-row">
              <div><label className="field-label" htmlFor="owner">GitHub owner</label><input id="owner" value={form.owner} onChange={set('owner')} /></div>
              <div><label className="field-label" htmlFor="repo">GitHub repository</label><input id="repo" value={form.repo} onChange={set('repo')} /></div>
            </div>
            <div className="field-row">
              <div><label className="field-label" htmlFor="board">Jira board ID</label><input id="board" inputMode="numeric" value={form.boardId} onChange={set('boardId')} /></div>
              <div><label className="field-label" htmlFor="sq">SonarQube project key</label><input id="sq" value={form.projectKey} onChange={set('projectKey')} /></div>
            </div>
            <p className="muted small">API tokens are configured on the server in <code>platform/server/.env</code>, never in the browser.</p>
            <div className="run-analysis">
              <button className="btn btn-primary" type="submit">Save settings</button>
              {saved && <span className={saved.kind === 'error' ? 'error small' : 'muted small'}>{saved.text}</span>}
            </div>
          </form>
        </section>
      )}
      {isManager && <NewProjectForm />}
    </div>
  );
}
