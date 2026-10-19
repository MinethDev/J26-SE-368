import { Router } from 'express';
import { AnalysisRun, Project } from '../models/index.js';
import { requireRole } from '../middleware/auth.js';
import { asyncHandler, HttpError } from '../middleware/errors.js';
import { checkComponentHealth, runAnalysis } from '../orchestrator/index.js';
import { COMPONENT_NAMES } from '../config.js';

const router = Router();

router.get(
  '/components/health',
  asyncHandler(async (req, res) => {
    res.json({ components: await checkComponentHealth() });
  })
);

// POST /api/orchestrator/run  { projectId, components?: ["pull-request"] }
router.post(
  '/run',
  requireRole('manager'),
  asyncHandler(async (req, res) => {
    const { projectId, components } = req.body || {};
    if (!projectId || !(await Project.exists({ key: projectId }))) throw new HttpError(404, 'Unknown projectId');
    if (components && (!Array.isArray(components) || components.some((c) => !COMPONENT_NAMES.includes(c)))) {
      throw new HttpError(400, `components must be a list drawn from: ${COMPONENT_NAMES.join(', ')}`);
    }
    const run = await runAnalysis(projectId, { triggeredBy: req.user.email, only: components });
    res.json({ run });
  })
);

router.get(
  '/runs',
  asyncHandler(async (req, res) => {
    const { projectId } = req.query;
    if (!projectId) throw new HttpError(400, 'projectId is required');
    res.json({ runs: await AnalysisRun.find({ projectId }).sort({ startedAt: -1 }).limit(20).lean() });
  })
);

export default router;
