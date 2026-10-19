import { Router } from 'express';
import mongoose from 'mongoose';
import { AnalysisRun, Insight } from '../models/index.js';
import { asyncHandler, HttpError } from '../middleware/errors.js';
import { COMPONENT_NAMES } from '../config.js';

const router = Router();

// GET /api/insights?projectId=...&component=...&latest=true
// latest=true (default) returns only insights from each component's most recent successful run.
router.get(
  '/',
  asyncHandler(async (req, res) => {
    const { projectId, component, latest = 'true' } = req.query;
    if (!projectId) throw new HttpError(400, 'projectId is required');
    if (component && !COMPONENT_NAMES.includes(component)) throw new HttpError(400, `Unknown component "${component}"`);

    const filter = { projectId };
    if (component) filter.component = component;

    if (latest === 'true') {
      const components = component ? [component] : COMPONENT_NAMES;
      const recentRuns = await AnalysisRun.find({ projectId }).sort({ startedAt: -1 }).limit(50).select('components').lean();
      const pairs = components
        .map((name) => {
          const run = recentRuns.find((r) => r.components.some((c) => c.component === name && c.status === 'ok'));
          return run ? { component: name, runId: run._id } : null;
        })
        .filter(Boolean);
      if (!pairs.length) return res.json({ insights: [] });
      filter.$or = pairs.map((p) => ({ component: p.component, runId: p.runId }));
      delete filter.component;
    }

    const insights = await Insight.find(filter).sort({ createdAt: -1 }).limit(500).lean();
    res.json({ insights });
  })
);

// Human-in-the-loop feedback: accept or reject a recommendation.
router.post(
  '/:id/feedback',
  asyncHandler(async (req, res) => {
    const { decision, comment } = req.body || {};
    if (!['accepted', 'rejected'].includes(decision)) throw new HttpError(400, 'decision must be "accepted" or "rejected"');
    if (!mongoose.isValidObjectId(req.params.id)) throw new HttpError(404, 'Insight not found');
    const insight = await Insight.findByIdAndUpdate(
      req.params.id,
      { feedback: { decision, comment, by: req.user.email, at: new Date() } },
      { new: true }
    ).lean();
    if (!insight) throw new HttpError(404, 'Insight not found');
    res.json({ insight });
  })
);

export default router;
