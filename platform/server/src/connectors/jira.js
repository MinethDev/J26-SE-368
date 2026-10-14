// Jira connector (owner: Wahalathanthri E. I.)
// Pulls sprints and their issues from a Jira Cloud Scrum board into the common data model.
// API docs: https://developer.atlassian.com/cloud/jira/software/rest/
import { config } from '../config.js';
import { Developer, Issue, Sprint } from '../models/index.js';
import { getJson, upsertMany } from './http.js';

function headers() {
  const { email, apiToken } = config.jira;
  if (!email || !apiToken) throw Object.assign(new Error('JIRA_EMAIL and JIRA_API_TOKEN must be set in .env'), { status: 400 });
  return { Authorization: `Basic ${Buffer.from(`${email}:${apiToken}`).toString('base64')}` };
}

// Jira descriptions can be plain strings or Atlassian Document Format objects.
function toText(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  const parts = [];
  (function walk(node) {
    if (node?.text) parts.push(node.text);
    (node?.content || []).forEach(walk);
  })(value);
  return parts.join(' ');
}

async function pageAll(path, key) {
  const out = [];
  for (let startAt = 0; ; ) {
    const sep = path.includes('?') ? '&' : '?';
    const page = await getJson(`${config.jira.baseUrl}${path}${sep}startAt=${startAt}&maxResults=100`, headers());
    const items = page[key] || [];
    out.push(...items);
    startAt += items.length;
    if (page.isLast === true || !items.length || (page.total !== undefined && startAt >= page.total)) break;
  }
  return out;
}

export async function syncJira(project) {
  const boardId = project.jira?.boardId;
  if (!config.jira.baseUrl) throw Object.assign(new Error('JIRA_BASE_URL must be set in .env'), { status: 400 });
  if (!boardId) throw Object.assign(new Error('Project has no Jira boardId configured'), { status: 400 });
  const projectId = project.key;
  const sp = config.jira.storyPointsField;
  const fields = `summary,description,issuetype,status,priority,assignee,reporter,labels,created,updated,resolutiondate,${sp}`;

  const sprints = await pageAll(`/rest/agile/1.0/board/${boardId}/sprint`, 'values');
  const developers = new Map();

  const toIssue = (raw, sprintId) => {
    const f = raw.fields;
    for (const person of [f.assignee, f.reporter]) {
      if (person?.accountId && !developers.has(person.accountId)) {
        developers.set(person.accountId, { projectId, source: 'jira', sourceId: person.accountId, name: person.displayName, email: person.emailAddress });
      }
    }
    return {
      projectId,
      source: 'jira',
      sourceId: raw.id,
      key: raw.key,
      summary: f.summary,
      description: toText(f.description),
      type: f.issuetype?.name,
      status: f.status?.name,
      statusCategory: f.status?.statusCategory?.name,
      priority: f.priority?.name,
      storyPoints: typeof f[sp] === 'number' ? f[sp] : null,
      assignee: f.assignee?.displayName,
      reporter: f.reporter?.displayName,
      sprintId: sprintId ? String(sprintId) : null,
      labels: f.labels || [],
      createdAt: f.created,
      updatedAt: f.updated,
      resolvedAt: f.resolutiondate,
    };
  };

  const issues = new Map();
  for (const s of sprints) {
    const sprintIssues = await pageAll(`/rest/agile/1.0/sprint/${s.id}/issue?fields=${fields}`, 'issues');
    sprintIssues.forEach((raw) => issues.set(raw.id, toIssue(raw, s.id)));
  }
  const backlog = await pageAll(`/rest/agile/1.0/board/${boardId}/backlog?fields=${fields}`, 'issues');
  backlog.forEach((raw) => issues.set(raw.id, toIssue(raw, null)));

  await upsertMany(
    Sprint,
    sprints.map((s) => ({
      projectId,
      source: 'jira',
      sourceId: String(s.id),
      name: s.name,
      state: s.state,
      goal: s.goal,
      startDate: s.startDate,
      endDate: s.endDate,
      completeDate: s.completeDate,
    }))
  );
  await upsertMany(Issue, [...issues.values()]);
  await upsertMany(Developer, [...developers.values()]);
  return { sprints: sprints.length, issues: issues.size, developers: developers.size };
}
