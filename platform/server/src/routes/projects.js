import { Router } from 'express';
import multer from 'multer';
import { Developer, Insight, Issue, Project, PullRequest, QualitySnapshot, Requirement, Sprint } from '../models/index.js';
import { requireRole } from '../middleware/auth.js';
import { asyncHandler, HttpError } from '../middleware/errors.js';
import { syncGithub } from '../connectors/github.js';
import { syncJira } from '../connectors/jira.js';
import { syncSonarqube } from '../connectors/sonarqube.js';
import { saveRequirementDocument } from '../connectors/upload.js';

const router = Router();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 10 * 1024 * 1024 } });

async function loadProject(key) {
  const project = await Project.findOne({ key });
  if (!project) throw new HttpError(404, `Project "${key}" not found`);
  return project;
}

router.get(
  '/',
  asyncHandler(async (req, res) => {
    res.json({ projects: await Project.find().sort({ name: 1 }).lean() });
  })
);

router.post(
  '/',
  requireRole('manager'),
  asyncHandler(async (req, res) => {
    const { key, name } = req.body || {};
    if (!key || !name) throw new HttpError(400, 'key and name are required');
    if (await Project.exists({ key })) throw new HttpError(409, `Project "${key}" already exists`);
    res.status(201).json({ project: await Project.create(req.body) });
  })
);

router.patch(
  '/:key',
  requireRole('manager'),
  asyncHandler(async (req, res) => {
    const project = await loadProject(req.params.key);
    for (const field of ['name', 'description', 'github', 'jira', 'sonarqube']) {
      if (req.body?.[field] !== undefined) project[field] = req.body[field];
    }
    await project.save();
    res.json({ project });
  })
);

// Counts of everything synced for a project (data-source health on the dashboard).
router.get(
  '/:key/summary',
  asyncHandler(async (req, res) => {
    const project = await loadProject(req.params.key);
    const q = { projectId: project.key };
    const [pullRequests, openPullRequests, issues, sprints, qualityFiles, requirements, developers, insights] = await Promise.all([
      PullRequest.countDocuments(q),
      PullRequest.countDocuments({ ...q, state: 'open' }),
      Issue.countDocuments(q),
      Sprint.countDocuments(q),
      QualitySnapshot.countDocuments(q),
      Requirement.countDocuments(q),
      Developer.countDocuments(q),
      Insight.countDocuments(q),
    ]);
    res.json({ project, counts: { pullRequests, openPullRequests, issues, sprints, qualityFiles, requirements, developers, insights } });
  })
);

const syncers = { github: syncGithub, jira: syncJira, sonarqube: syncSonarqube };

router.post(
  '/:key/sync/:source',
  requireRole('manager'),
  asyncHandler(async (req, res) => {
    const sync = syncers[req.params.source];
    if (!sync) throw new HttpError(400, `Unknown source "${req.params.source}". Use: ${Object.keys(syncers).join(', ')}`);
    const project = await loadProject(req.params.key);
    const result = await sync(project, req.body || {});
    project.set(`lastSync.${req.params.source}`, new Date());
    await project.save();
    res.json({ source: req.params.source, result });
  })
);

router.post(
  '/:key/requirements',
  requireRole('manager'),
  upload.single('file'),
  asyncHandler(async (req, res) => {
    if (!req.file) throw new HttpError(400, 'Attach a file in the "file" field');
    const project = await loadProject(req.params.key);
    const result = await saveRequirementDocument(project, req.file);
    project.set('lastSync.upload', new Date());
    await project.save();
    res.status(201).json(result);
  })
);

// Read access to the common data model, used by component pages.
const readers = {
  'pull-requests': (q) => PullRequest.find(q).select('-raw -files.patch').sort({ createdAt: -1 }).limit(200),
  issues: (q) => Issue.find(q).select('-raw').sort({ createdAt: -1 }).limit(1000),
  sprints: (q) => Sprint.find(q).select('-raw').sort({ startDate: -1 }),
  quality: (q) => QualitySnapshot.find(q).select('-raw').limit(2000),
  requirements: (q) => Requirement.find(q).select('-raw').sort({ syncedAt: -1 }),
  developers: (q) => Developer.find(q).select('-raw'),
};

router.get(
  '/:key/data/:kind',
  asyncHandler(async (req, res) => {
    const read = readers[req.params.kind];
    if (!read) throw new HttpError(404, `Unknown data kind "${req.params.kind}"`);
    const project = await loadProject(req.params.key);
    res.json({ items: await read({ projectId: project.key }).lean() });
  })
);

export default router;
