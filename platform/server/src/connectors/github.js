// GitHub connector (owner: Perera W. M. M.)
// Pulls repository info, pull requests, changed files and reviews into the common data model.
// API docs: https://docs.github.com/en/rest/pulls
import { config } from '../config.js';
import { Developer, PullRequest, Repository } from '../models/index.js';
import { getJson, mapLimit, upsertMany } from './http.js';

const API = 'https://api.github.com';

const isBot = (user) => !!user && (user.type === 'Bot' || /\[bot\]$/i.test(user.login || ''));

function headers() {
  const h = { 'X-GitHub-Api-Version': '2022-11-28', Accept: 'application/vnd.github+json' };
  if (config.github.token) h.Authorization = `Bearer ${config.github.token}`;
  return h;
}

async function paginate(path, { max = Infinity } = {}) {
  const out = [];
  for (let page = 1; out.length < max; page++) {
    const sep = path.includes('?') ? '&' : '?';
    const batch = await getJson(`${API}${path}${sep}per_page=100&page=${page}`, headers());
    out.push(...batch);
    if (batch.length < 100) break;
  }
  return out.slice(0, max);
}

// CI status for a commit, combining GitHub check runs (Actions) and legacy commit statuses.
export function summarizeCi(checkRuns, combinedStatus) {
  const runs = checkRuns || [];
  const statuses = combinedStatus?.statuses || [];
  if (!runs.length && !statuses.length) return { ci: null, total: 0, failing: [], pending: [] };

  const FAILED = ['failure', 'timed_out', 'cancelled', 'action_required', 'startup_failure'];
  const failing = [
    ...runs.filter((r) => r.status === 'completed' && FAILED.includes(r.conclusion)).map((r) => r.name),
    ...statuses.filter((s) => ['failure', 'error'].includes(s.state)).map((s) => s.context),
  ];
  const pending = [
    ...runs.filter((r) => r.status !== 'completed').map((r) => r.name),
    ...statuses.filter((s) => s.state === 'pending').map((s) => s.context),
  ];
  const ci = failing.length ? 'fail' : pending.length ? 'pending' : 'pass';
  return { ci, total: runs.length + statuses.length, failing, pending };
}

// GitHub computes mergeability lazily: null means "not computed yet".
export function summarizeConflicts(mergeable) {
  if (mergeable === true) return 'pass';
  if (mergeable === false) return 'fail';
  return null;
}

// Extra data for open PRs only (merge-readiness): CI, conflicts and inline review comments.
async function openPrExtras(fullName, detail) {
  const base = `/repos/${fullName}`;
  const sha = detail.head?.sha;
  const [checkRuns, combinedStatus, comments] = await Promise.all([
    sha ? getJson(`${API}${base}/commits/${sha}/check-runs?per_page=100`, headers()).then((r) => r.check_runs).catch(() => null) : null,
    sha ? getJson(`${API}${base}/commits/${sha}/status`, headers()).catch(() => null) : null,
    paginate(`${base}/pulls/${detail.number}/comments`, { max: 300 }).catch(() => []),
  ]);
  const ci = checkRuns === null && combinedStatus === null ? { ci: null, total: 0, failing: [], pending: [] } : summarizeCi(checkRuns, combinedStatus);
  return {
    checks: {
      ci: ci.ci,
      merge_conflicts: summarizeConflicts(detail.mergeable),
      quality_gate: null, // SonarQube quality gates are not linked to PRs yet
      details: { ciTotal: ci.total, ciFailing: ci.failing, ciPending: ci.pending, mergeableState: detail.mergeable_state },
    },
    reviewComments: comments
      .filter((c) => c.user)
      .map((c) => ({
        id: c.id,
        inReplyTo: c.in_reply_to_id ?? null,
        author: c.user.login,
        authorIsBot: isBot(c.user),
        path: c.path,
        createdAt: c.created_at,
      })),
  };
}

function prState(pr) {
  if (pr.merged_at) return 'merged';
  return pr.state === 'closed' ? 'closed' : 'open';
}

/**
 * Syncs the project's GitHub repository.
 * @param {object} project  Project document with github.owner and github.repo
 * @param {{ maxPullRequests?: number }} options
 */
export async function syncGithub(project, { maxPullRequests = 400 } = {}) {
  const { owner, repo } = project.github || {};
  if (!owner || !repo) throw Object.assign(new Error('Project has no GitHub owner/repo configured'), { status: 400 });
  const projectId = project.key;
  const fullName = `${owner}/${repo}`;

  const repoInfo = await getJson(`${API}/repos/${fullName}`, headers());
  await upsertMany(Repository, [
    {
      projectId,
      source: 'github',
      sourceId: String(repoInfo.id),
      fullName: repoInfo.full_name,
      defaultBranch: repoInfo.default_branch,
      description: repoInfo.description,
      url: repoInfo.html_url,
    },
  ]);

  const list = await paginate(`/repos/${fullName}/pulls?state=all&sort=created&direction=desc`, { max: maxPullRequests });

  const developers = new Map();
  const addDev = (user) => {
    if (user?.login && !developers.has(user.login)) {
      developers.set(user.login, { projectId, source: 'github', sourceId: String(user.id), login: user.login, isBot: isBot(user) });
    }
  };

  const prs = await mapLimit(list, 5, async (item) => {
    const base = `/repos/${fullName}/pulls/${item.number}`;
    const [detail, files, reviews] = await Promise.all([
      getJson(`${API}${base}`, headers()),
      paginate(`${base}/files`, { max: 300 }),
      paginate(`${base}/reviews`),
    ]);
    addDev(detail.user);
    reviews.forEach((r) => addDev(r.user));
        const extras = prState(detail) === 'open' ? await openPrExtras(fullName, detail) : { checks: null, reviewComments: [] };
    return {
      projectId,
      source: 'github',
      sourceId: String(detail.id),
      repo: fullName,
      number: detail.number,
      title: detail.title,
      body: detail.body || '',
      author: detail.user?.login,
      authorIsBot: isBot(detail.user),
      state: prState(detail),
      draft: detail.draft,
      createdAt: detail.created_at,
      updatedAt: detail.updated_at,
      mergedAt: detail.merged_at,
      closedAt: detail.closed_at,
      baseBranch: detail.base?.ref,
      headBranch: detail.head?.ref,
      url: detail.html_url,
      additions: detail.additions,
      deletions: detail.deletions,
      changedFiles: detail.changed_files,
      commits: detail.commits,
      labels: (detail.labels || []).map((l) => l.name),
      requestedReviewers: (detail.requested_reviewers || []).map((u) => u.login),
      files: files.map((f) => ({ path: f.filename, status: f.status, additions: f.additions, deletions: f.deletions, patch: f.patch })),
      reviews: reviews
        .filter((r) => r.user)
        .map((r) => ({ reviewer: r.user.login, reviewerIsBot: isBot(r.user), state: r.state, submittedAt: r.submitted_at, body: r.body })),
              ...extras,
    };
  });

  await upsertMany(PullRequest, prs);
  await upsertMany(Developer, [...developers.values()]);
  return { repository: fullName, pullRequests: prs.length, developers: developers.size };
}
