// Gathers the data each component needs from the common data model (Contract 1)
// and shapes it into the `context` of its POST /analyze request (Contract 3).
// Component owners: if you need more fields, add them here and update docs/CONTRACTS.md.
import { Issue, PullRequest, QualitySnapshot, Repository, Requirement, Sprint } from '../models/index.js';

const MAX_PATCH_CHARS = 4000; // keep request size reasonable for LLM-based analysis

const lean = (query) => query.select('-raw -__v').lean();

async function planning(projectId) {
  const [requirements, issues] = await Promise.all([
    lean(Requirement.find({ projectId }).sort({ syncedAt: -1 }).limit(10)),
    lean(Issue.find({ projectId }).sort({ createdAt: -1 }).limit(1000)),
  ]);
  return { requirements, issues };
}

async function sprint(projectId) {
  const [sprints, issues] = await Promise.all([
    lean(Sprint.find({ projectId }).sort({ startDate: -1 }).limit(20)),
    lean(Issue.find({ projectId, sprintId: { $ne: null } }).limit(2000)),
  ]);
  return { sprints, issues };
}

async function quality(projectId) {
  const [repository, qualitySnapshots, pullRequests] = await Promise.all([
    lean(Repository.findOne({ projectId })),
    lean(QualitySnapshot.find({ projectId }).limit(5000)),
    lean(PullRequest.find({ projectId }).select('-files.patch').sort({ createdAt: -1 }).limit(200)),
  ]);
  return { repository, qualitySnapshots, pullRequests };
}

async function pullRequest(projectId) {
  const [repository, openPrs, history] = await Promise.all([
    lean(Repository.findOne({ projectId })),
    lean(PullRequest.find({ projectId, state: 'open' }).sort({ createdAt: -1 }).limit(30)),
    // Past PRs (with who reviewed them) for reviewer recommendation and merge-readiness baselines.
    lean(PullRequest.find({ projectId, state: { $ne: 'open' } }).select('-files.patch -body').sort({ createdAt: -1 }).limit(500)),
  ]);
  for (const pr of openPrs) {
    for (const f of pr.files || []) {
      if (f.patch && f.patch.length > MAX_PATCH_CHARS) f.patch = `${f.patch.slice(0, MAX_PATCH_CHARS)}\n... (truncated)`;
    }
  }
  return { repository, pullRequests: openPrs, history };
}

export const contextBuilders = {
  planning,
  sprint,
  quality,
  'pull-request': pullRequest,
};

// Which earlier components' insights each component receives (the intelligence flow).
export const upstreamOf = {
  planning: [],
  sprint: ['planning'],
  quality: [],
  'pull-request': ['quality'],
};
