// Creates demo accounts and the demo project.
//   npm run seed              -> users + project only
//   npm run seed -- --sample  -> also inserts a small SAMPLE dataset (sourceId starts with "sample-")
//                                so pages have something to show before connectors are configured.
// Remove sample data any time with:  npm run seed -- --clear-sample
import bcrypt from 'bcryptjs';
import { connectDb, disconnectDb } from '../db.js';
import { Issue, Project, PullRequest, QualitySnapshot, Sprint, User } from '../models/index.js';

const args = new Set(process.argv.slice(2));
const PROJECT_KEY = 'devintel-demo';

const USERS = [
  { email: 'manager@devintel.local', name: 'Demo Manager', role: 'manager', password: 'devintel-manager' },
  { email: 'developer@devintel.local', name: 'Demo Developer', role: 'developer', password: 'devintel-developer' },
];

async function seedUsers() {
  for (const u of USERS) {
    if (await User.exists({ email: u.email })) continue;
    await User.create({ email: u.email, name: u.name, role: u.role, passwordHash: await bcrypt.hash(u.password, 10) });
    console.log(`  created ${u.role}: ${u.email} / ${u.password}`);
  }
}

async function seedProject() {
  await Project.updateOne(
    { key: PROJECT_KEY },
    {
      $setOnInsert: {
        key: PROJECT_KEY,
        name: 'DevIntel Demo Project',
        description: 'Demo project linking one GitHub repo, one Jira board and one SonarQube project.',
        github: { owner: 'MinethDev', repo: 'J26-SE-368' },
        jira: { boardId: null },
        sonarqube: { projectKey: 'devintel-demo' },
      },
    },
    { upsert: true }
  );
  console.log(`  project: ${PROJECT_KEY} (edit its GitHub/Jira/SonarQube settings on the Data Sources page)`);
}

const SAMPLE = { projectId: PROJECT_KEY };
const day = (n) => new Date(Date.UTC(2026, 8, 1) + n * 86400000);

async function seedSample() {
  const people = ['nimal', 'kasun', 'dilini', 'tharindu'];
  const prs = Array.from({ length: 12 }, (_, i) => {
    const author = people[i % 4];
    const reviewer = people[(i + 1) % 4];
    const open = i >= 9;
    return {
      ...SAMPLE,
      source: 'github',
      sourceId: `sample-pr-${i + 1}`,
      repo: 'sample/devintel-demo',
      number: i + 1,
      title: ['Add login rate limiting', 'Refactor sprint service', 'Fix null check in PR parser', 'Add SonarQube sync job'][i % 4],
      body: 'Sample pull request for demonstration.',
      author,
      state: open ? 'open' : i % 5 === 0 ? 'closed' : 'merged',
      createdAt: day(i * 2),
      mergedAt: open || i % 5 === 0 ? null : day(i * 2 + 1),
      additions: 20 + i * 15,
      deletions: 5 + i * 3,
      changedFiles: 1 + (i % 4),
      files: [{ path: `src/module${i % 3}/service.js`, status: 'modified', additions: 20 + i * 15, deletions: 5 + i * 3, patch: '@@ -1,3 +1,4 @@\n+// sample change' }],
      reviews: open && i === 11 ? [] : [{ reviewer, state: 'APPROVED', submittedAt: day(i * 2 + 1) }],
    };
  });
  const sprints = [0, 1, 2].map((s) => ({
    ...SAMPLE,
    source: 'jira',
    sourceId: `sample-sprint-${s + 1}`,
    name: `Sprint ${s + 1}`,
    state: s < 2 ? 'closed' : 'active',
    startDate: day(s * 14),
    endDate: day(s * 14 + 14),
    completeDate: s < 2 ? day(s * 14 + 14) : null,
  }));
  const issues = Array.from({ length: 24 }, (_, i) => ({
    ...SAMPLE,
    source: 'jira',
    sourceId: `sample-issue-${i + 1}`,
    key: `DEV-${i + 1}`,
    summary: `Sample task ${i + 1}`,
    type: i % 5 === 0 ? 'Bug' : 'Story',
    status: i < 16 || i % 3 === 0 ? 'Done' : 'In Progress',
    statusCategory: i < 16 || i % 3 === 0 ? 'Done' : 'In Progress',
    storyPoints: [1, 2, 3, 5, 8][i % 5],
    assignee: people[i % 4],
    sprintId: `sample-sprint-${Math.floor(i / 8) + 1}`,
    createdAt: day(Math.floor(i / 8) * 14),
  }));
  const quality = Array.from({ length: 8 }, (_, i) => ({
    ...SAMPLE,
    source: 'sonarqube',
    sourceId: `sample-file-${i + 1}`,
    path: `src/module${i % 3}/file${i}.js`,
    language: 'js',
    metrics: { ncloc: 80 + i * 40, complexity: 5 + i * 4, code_smells: i * 2, bugs: i % 3, vulnerabilities: i === 6 ? 1 : 0, sqale_index: i * 25, coverage: 80 - i * 8 },
    issueCounts: { MAJOR: i, MINOR: i * 2 },
    snapshotAt: day(40),
  }));
  const bulk = (Model, docs) =>
    Model.bulkWrite(docs.map((d) => ({ updateOne: { filter: { projectId: d.projectId, source: d.source, sourceId: d.sourceId }, update: { $set: d }, upsert: true } })));
  await Promise.all([bulk(PullRequest, prs), bulk(Sprint, sprints), bulk(Issue, issues), bulk(QualitySnapshot, quality)]);
  console.log(`  sample data: ${prs.length} PRs, ${sprints.length} sprints, ${issues.length} issues, ${quality.length} quality files`);
}

async function clearSample() {
  const q = { projectId: PROJECT_KEY, sourceId: /^sample-/ };
  await Promise.all([PullRequest.deleteMany(q), Sprint.deleteMany(q), Issue.deleteMany(q), QualitySnapshot.deleteMany(q)]);
  console.log('  sample data removed');
}

await connectDb();
console.log('[seed]');
await seedUsers();
await seedProject();
if (args.has('--sample')) await seedSample();
if (args.has('--clear-sample')) await clearSample();
await disconnectDb();
