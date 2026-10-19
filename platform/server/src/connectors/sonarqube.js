// SonarQube connector (owner: Senura Virantha S.J.)
// Pulls file-level quality metrics and open issue counts into the common data model.
// API docs: <your SonarQube server>/web_api  (api/measures/component_tree, api/issues/search)
import { config } from '../config.js';
import { QualitySnapshot } from '../models/index.js';
import { getJson, upsertMany } from './http.js';

export const METRIC_KEYS = [
  'ncloc',
  'complexity',
  'cognitive_complexity',
  'code_smells',
  'bugs',
  'vulnerabilities',
  'security_hotspots',
  'sqale_index', // technical debt in minutes
  'coverage',
  'duplicated_lines_density',
];

function headers() {
  // A user token works as the username with an empty password on all recent SonarQube versions.
  return config.sonarqube.token ? { Authorization: `Basic ${Buffer.from(`${config.sonarqube.token}:`).toString('base64')}` } : {};
}

const parseValue = (v) => (v === undefined || v === '' || Number.isNaN(Number(v)) ? v : Number(v));

export async function syncSonarqube(project) {
  const key = project.sonarqube?.projectKey;
  if (!key) throw Object.assign(new Error('Project has no SonarQube projectKey configured'), { status: 400 });
  const projectId = project.key;
  const base = config.sonarqube.url.replace(/\/$/, '');

  const files = [];
  for (let p = 1; ; p++) {
    const page = await getJson(
      `${base}/api/measures/component_tree?component=${encodeURIComponent(key)}&qualifiers=FIL&metricKeys=${METRIC_KEYS.join(',')}&ps=500&p=${p}`,
      headers()
    );
    files.push(...page.components);
    if (page.paging.pageIndex * page.paging.pageSize >= page.paging.total) break;
  }

  // Open issue counts per file, by severity (api/issues/search returns at most 10,000 issues).
  const issueCounts = new Map();
  for (let p = 1; p <= 20; p++) {
    const page = await getJson(`${base}/api/issues/search?componentKeys=${encodeURIComponent(key)}&resolved=false&ps=500&p=${p}`, headers());
    for (const issue of page.issues) {
      const counts = issueCounts.get(issue.component) || {};
      const sev = issue.severity || 'UNKNOWN';
      counts[sev] = (counts[sev] || 0) + 1;
      issueCounts.set(issue.component, counts);
    }
    if (p * 500 >= Math.min(page.paging?.total ?? page.total ?? 0, 10000)) break;
  }

  const snapshotAt = new Date();
  await upsertMany(
    QualitySnapshot,
    files.map((f) => ({
      projectId,
      source: 'sonarqube',
      sourceId: f.key,
      path: f.path,
      language: f.language,
      metrics: Object.fromEntries((f.measures || []).map((m) => [m.metric, parseValue(m.value)])),
      issueCounts: issueCounts.get(f.key) || {},
      snapshotAt,
    }))
  );
  return { files: files.length, filesWithIssues: issueCounts.size };
}
