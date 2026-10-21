// Contract 1: the common data model. Connectors normalise each tool's data into
// these collections. See docs/CONTRACTS.md.
import mongoose from 'mongoose';

const { Schema } = mongoose;

const SOURCES = ['github', 'jira', 'sonarqube', 'upload'];

// Fields every normalised entity carries, so data from different tools can be linked
// and re-running a sync updates records instead of duplicating them.
const sourceFields = {
  projectId: { type: String, required: true, index: true },
  source: { type: String, enum: SOURCES, required: true },
  sourceId: { type: String, required: true },
  raw: { type: Schema.Types.Mixed, select: false }, // original payload, kept for debugging
};

function entity(name, fields) {
  const schema = new Schema({ ...sourceFields, ...fields }, { timestamps: { createdAt: 'syncedAt', updatedAt: 'updatedSyncAt' } });
  schema.index({ projectId: 1, source: 1, sourceId: 1 }, { unique: true });
  return mongoose.model(name, schema);
}

export const Developer = entity('Developer', {
  login: { type: String, index: true },
  name: String,
  email: String,
  isBot: { type: Boolean, default: false },
});

export const Repository = entity('Repository', {
  fullName: String,
  defaultBranch: String,
  description: String,
  url: String,
});

export const PullRequest = entity('PullRequest', {
  repo: String, // owner/repo
  number: { type: Number, index: true },
  title: String,
  body: String,
  author: String,
  authorIsBot: Boolean,
  state: { type: String, enum: ['open', 'closed', 'merged'] },
  draft: Boolean,
  createdAt: Date,
  updatedAt: Date,
  mergedAt: Date,
  closedAt: Date,
  baseBranch: String,
  headBranch: String,
  url: String,
  additions: Number,
  deletions: Number,
  changedFiles: Number,
  commits: Number,
  labels: [String],
  requestedReviewers: [String],
  files: [{ _id: false, path: String, status: String, additions: Number, deletions: Number, patch: String }],
    // Open PRs only: CI / merge-conflict status and inline review comments (for merge-readiness).
  checks: Schema.Types.Mixed, // { ci: 'pass'|'fail'|'pending'|null, merge_conflicts: 'pass'|'fail'|null, quality_gate: null, details }
  reviewComments: [{ _id: false, id: Number, inReplyTo: Number, author: String, authorIsBot: Boolean, path: String, createdAt: Date }],
  reviews: [{ _id: false, reviewer: String, reviewerIsBot: Boolean, state: String, submittedAt: Date, body: String }],
});

export const Issue = entity('Issue', {
  key: { type: String, index: true },
  summary: String,
  description: String,
  type: String,
  status: String,
  statusCategory: String, // 'To Do' | 'In Progress' | 'Done'
  priority: String,
  storyPoints: Number,
  assignee: String,
  reporter: String,
  sprintId: { type: String, index: true },
  labels: [String],
  createdAt: Date,
  updatedAt: Date,
  resolvedAt: Date,
    // Jira change history for sprint, status and story point changes (used by the sprint component).
  changelog: [{ _id: false, field: String, from: String, to: String, at: Date }],
});

export const Sprint = entity('Sprint', {
  name: String,
  state: { type: String, enum: ['future', 'active', 'closed'] },
  goal: String,
  startDate: Date,
  endDate: Date,
  completeDate: Date,
});

export const QualitySnapshot = entity('QualitySnapshot', {
  path: { type: String, index: true },
  language: String,
  metrics: Schema.Types.Mixed, // e.g. { ncloc, complexity, cognitive_complexity, code_smells, bugs, vulnerabilities, sqale_index, coverage, duplicated_lines_density }
  issueCounts: Schema.Types.Mixed, // e.g. { BLOCKER: 0, CRITICAL: 1, MAJOR: 3, MINOR: 2, INFO: 0 }
  snapshotAt: Date,
});

export const Requirement = entity('Requirement', {
  fileName: String,
  mimeType: String,
  rawText: String,
  // Filled by Requirement Intelligence (planning service) once extraction is implemented.
  items: [{ _id: false, id: String, text: String, kind: { type: String, enum: ['functional', 'non-functional', 'constraint', 'other'] } }],
});
