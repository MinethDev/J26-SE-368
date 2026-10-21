// DevIntel PP1 evidence check: integration, system and non-functional measurements.
// Needs only Node 20+ (no packages). Run it while MongoDB, the 4 services and the platform API are running:
//
//   node evidence_check.mjs
//
// Settings (optional environment variables):
//   BASE=http://localhost:4000   PROJECT=devintel-demo   RUNS=5   SAMPLES=20
//   EMAIL / PASSWORD             manager login (default: the seeded manager)
//   DEV_EMAIL / DEV_PASSWORD     developer login, for the role check (default: the seeded developer)
// Results are printed and saved to evidence_results.json in the current folder.
import { writeFileSync } from 'node:fs';

const BASE = process.env.BASE || 'http://localhost:4000';
const PROJECT = process.env.PROJECT || 'devintel-demo';
const RUNS = Number(process.env.RUNS || 5);
const SAMPLES = Number(process.env.SAMPLES || 20);
const EMAIL = process.env.EMAIL || 'manager@devintel.local';
const PASSWORD = process.env.PASSWORD || 'devintel-manager';
const DEV_EMAIL = process.env.DEV_EMAIL || 'developer@devintel.local';
const DEV_PASSWORD = process.env.DEV_PASSWORD || 'devintel-developer';
const COMPONENTS = ['planning', 'sprint', 'quality', 'pull-request'];

const results = { when: new Date().toISOString(), base: BASE, project: PROJECT, checks: [], timings: {}, runs: [] };
const check = (area, name, pass, detail = '') => {
  results.checks.push({ area, name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  [${area}] ${name}${detail ? ` - ${detail}` : ''}`);
};

async function call(path, { method = 'GET', token, body } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const t0 = performance.now();
  const res = await fetch(`${BASE}/api${path}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  const ms = performance.now() - t0;
  const data = await res.json().catch(() => ({}));
  return { status: res.status, data, ms };
}

const pct = (arr, p) => {
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1)];
};
const stats = (arr) => ({ n: arr.length, min: Math.min(...arr), median: pct(arr, 50), p95: pct(arr, 95), max: Math.max(...arr) });
const r = (x) => Math.round(x);

async function login(email, password) {
  const res = await call('/auth/login', { method: 'POST', body: { email, password } });
  return res.status === 200 ? res.data.token : null;
}

// ---------- Security: authentication and role-based access ----------
const token = await login(EMAIL, PASSWORD);
check('Security', 'Manager can sign in', !!token);
if (!token) {
  console.error('Cannot continue without a manager login. Check EMAIL / PASSWORD.');
  process.exit(1);
}
const wrong = await call('/auth/login', { method: 'POST', body: { email: EMAIL, password: 'wrong-password' } });
check('Security', 'Wrong password is refused', wrong.status === 401, `HTTP ${wrong.status}`);
const anon = await call(`/insights?projectId=${PROJECT}`);
check('Security', 'API refuses requests without a login', anon.status === 401, `HTTP ${anon.status}`);
const forged = await call(`/insights?projectId=${PROJECT}`, { token: 'not-a-real-token' });
check('Security', 'API refuses a forged token', forged.status === 401, `HTTP ${forged.status}`);
const devToken = await login(DEV_EMAIL, DEV_PASSWORD);
if (devToken) {
  const devRun = await call('/orchestrator/run', { method: 'POST', token: devToken, body: { projectId: PROJECT } });
  check('Security', 'Developer role cannot start an analysis (manager only)', devRun.status === 403, `HTTP ${devRun.status}`);
  const devSync = await call(`/projects/${PROJECT}/sync/github`, { method: 'POST', token: devToken, body: {} });
  check('Security', 'Developer role cannot sync data sources (manager only)', devSync.status === 403, `HTTP ${devSync.status}`);
} else {
  console.log('SKIP  [Security] developer login not available, role check skipped');
}
const me = await call('/auth/me', { token });
check('Security', 'Password hash is never returned by the API', me.status === 200 && !JSON.stringify(me.data).toLowerCase().includes('hash'));

// ---------- Robustness: invalid input ----------
const noProject = await call('/insights', { token });
check('Robustness', 'Missing projectId is rejected with a clear message', noProject.status === 400, `HTTP ${noProject.status}: ${noProject.data.error}`);
const badComponent = await call(`/insights?projectId=${PROJECT}&component=nope`, { token });
check('Robustness', 'Unknown component name is rejected', badComponent.status === 400, `HTTP ${badComponent.status}: ${badComponent.data.error}`);

// ---------- Health of the 4 AI services ----------
const health = await call('/orchestrator/components/health', { token });
for (const c of health.data.components || []) {
  check('Availability', `${c.component} service is up`, !!c.up, c.modelVersion || c.error || '');
}

// ---------- Performance: API response time ----------
const endpoints = {
  'GET /projects/:id/summary': `/projects/${PROJECT}/summary`,
  'GET /insights (all components)': `/insights?projectId=${PROJECT}`,
  'GET /orchestrator/components/health': '/orchestrator/components/health',
};
for (const [label, path] of Object.entries(endpoints)) {
  const times = [];
  for (let i = 0; i < SAMPLES; i++) times.push((await call(path, { token })).ms);
  results.timings[label] = Object.fromEntries(Object.entries(stats(times)).map(([k, v]) => [k, k === 'n' ? v : r(v)]));
  console.log(`TIME  ${label}: median ${r(pct(times, 50))} ms, p95 ${r(pct(times, 95))} ms (n=${SAMPLES})`);
}

// ---------- System + reliability: repeated full analysis runs ----------
for (let i = 1; i <= RUNS; i++) {
  const res = await call('/orchestrator/run', { method: 'POST', token, body: { projectId: PROJECT } });
  const run = res.data.run;
  if (!run) {
    check('Reliability', `Full analysis run ${i}`, false, `HTTP ${res.status}: ${res.data.error}`);
    continue;
  }
  results.runs.push({
    run: i,
    status: run.status,
    totalMs: r(res.ms),
    components: run.components.map((c) => ({ component: c.component, status: c.status, ms: c.durationMs, insights: c.insightCount, rejected: c.rejectedCount })),
  });
  console.log(`RUN   ${i}/${RUNS}: ${run.status} in ${(res.ms / 1000).toFixed(1)} s - ` +
    run.components.map((c) => `${c.component} ${c.status} ${c.durationMs} ms, ${c.insightCount ?? 0} insights`).join('; '));
}
const okRuns = results.runs.filter((x) => x.status === 'completed').length;
check('Reliability', `Full analysis completed in every repeated run`, okRuns === RUNS, `${okRuns}/${RUNS} runs completed`);
const rejected = results.runs.flatMap((x) => x.components).reduce((n, c) => n + (c.rejected || 0), 0);
check('Integration', 'Every insight passed contract validation (none rejected)', rejected === 0, `${rejected} rejected`);
for (const name of COMPONENTS) {
  const ms = results.runs.flatMap((x) => x.components).filter((c) => c.component === name && c.status === 'ok').map((c) => c.ms);
  if (ms.length) results.timings[`analysis: ${name}`] = Object.fromEntries(Object.entries(stats(ms)).map(([k, v]) => [k, k === 'n' ? v : r(v)]));
}
const totals = results.runs.map((x) => x.totalMs);
if (totals.length) results.timings['analysis: full run (all 4)'] = Object.fromEntries(Object.entries(stats(totals)).map(([k, v]) => [k, k === 'n' ? v : r(v)]));

// ---------- Integration: data flowing between components ----------
const all = (await call(`/insights?projectId=${PROJECT}`, { token })).data.insights || [];
const byComp = Object.fromEntries(COMPONENTS.map((c) => [c, all.filter((i) => i.component === c)]));
for (const c of COMPONENTS) check('Integration', `${c} insights stored in the knowledge repository`, byComp[c].length > 0, `${byComp[c].length} insights`);
const usesBaseline = byComp.sprint.filter((i) => (i.evidence || []).some((e) => e.ref === 'planning:planning-baseline'));
check('Integration', 'Planning -> Sprint: sprint insights cite the planning baseline', usesBaseline.length > 0, `${usesBaseline.length} sprint insight(s)`);
const hotspots = byComp.quality.filter((i) => i.type === 'quality-hotspot');
const usesHotspot = byComp['pull-request'].filter((i) => (i.evidence || []).some((e) => String(e.ref).startsWith('quality:')));
check('Integration', 'Quality -> Pull Request: PR insights cite quality hotspots', usesHotspot.length > 0,
  `${hotspots.length} hotspot(s), ${usesHotspot.length} PR insight(s) cite one` +
  (usesHotspot.length ? '' : ' (needs an OPEN PR that changes a hotspot file, e.g. PR #9)'));

// Fallback: Pull Request alone still receives the last saved quality hotspots.
const solo = await call('/orchestrator/run', { method: 'POST', token, body: { projectId: PROJECT, components: ['pull-request'] } });
const afterSolo = (await call(`/insights?projectId=${PROJECT}&component=pull-request`, { token })).data.insights || [];
const soloCites = afterSolo.filter((i) => (i.evidence || []).some((e) => String(e.ref).startsWith('quality:')));
check('Integration', 'Pull Request run on its own still uses the latest saved quality hotspots',
  solo.data.run?.status === 'completed' && soloCites.length > 0, `${soloCites.length} PR insight(s) cite a hotspot`);

// ---------- Explainability ----------
const explained = all.filter((i) => (i.explanation || []).length > 0);
check('Explainability', 'Insights carry an explanation (what drove the result)', explained.length > 0, `${explained.length}/${all.length} insights`);
const withActions = all.filter((i) => (i.recommendations || []).length > 0);
check('Explainability', 'Insights carry recommended actions', withActions.length > 0, `${withActions.length}/${all.length} insights`);

const passed = results.checks.filter((c) => c.pass).length;
console.log(`\n${passed}/${results.checks.length} checks passed.`);
writeFileSync('evidence_results.json', JSON.stringify(results, null, 2));
console.log('Saved evidence_results.json');
