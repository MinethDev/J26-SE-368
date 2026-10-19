// AI Orchestrator: for each component (in order), gather context, call its /analyze
// endpoint, validate the returned insights and store them in the Knowledge Repository.
import { config } from '../config.js';
import { AnalysisRun, Insight } from '../models/index.js';
import { contextBuilders, upstreamOf } from './contextBuilders.js';
import { validateInsight } from './validateInsight.js';

// Strip Mongo-specific fields so components receive plain JSON.
const toPlain = (docs) => JSON.parse(JSON.stringify(docs));

async function callComponent(component, body) {
  const res = await fetch(`${component.url}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(config.serviceTimeoutMs),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status} from ${component.name} service: ${text.slice(0, 300)}`);
  }
  return res.json();
}

export async function checkComponentHealth() {
  return Promise.all(
    config.components.map(async (c) => {
      try {
        const res = await fetch(`${c.url}/health`, { signal: AbortSignal.timeout(3000) });
        const body = await res.json();
        return { component: c.name, url: c.url, up: res.ok, ...body };
      } catch (err) {
        return { component: c.name, url: c.url, up: false, error: err.cause?.code || err.message };
      }
    })
  );
}

/**
 * Runs the full analysis for a project.
 * @param {string} projectId
 * @param {{ triggeredBy?: string, only?: string[] }} options  `only` limits the run to some components
 */
export async function runAnalysis(projectId, { triggeredBy, only } = {}) {
  const selected = config.components.filter((c) => !only || only.includes(c.name));
  const run = await AnalysisRun.create({
    projectId,
    triggeredBy,
    startedAt: new Date(),
    components: selected.map((c) => ({ component: c.name })),
  });

  const produced = {}; // component name -> insights produced in this run (for upstream)

  for (const component of selected) {
    const result = run.components.find((r) => r.component === component.name);
    const started = Date.now();
    try {
      const context = toPlain(await contextBuilders[component.name](projectId));
      const upstream = {};
      for (const name of upstreamOf[component.name]) upstream[name] = produced[name] || [];

      const response = await callComponent(component, { projectId, context, upstream });
      const insights = Array.isArray(response.insights) ? response.insights : [];

      const valid = [];
      const errorMessages = [];
      insights.forEach((insight, i) => {
        const { ok, errors } = validateInsight(insight);
        if (ok && insight.component === component.name) valid.push(insight);
        else errorMessages.push(`insight[${i}]: ${ok ? `component must be "${component.name}"` : errors.join('; ')}`);
      });

      if (valid.length) {
        await Insight.insertMany(valid.map((ins) => ({ ...ins, projectId, runId: run._id })));
      }
      produced[component.name] = valid;

      Object.assign(result, {
        status: 'ok',
        modelVersion: response.modelVersion,
        insightCount: valid.length,
        rejectedCount: errorMessages.length,
        errorMessages: errorMessages.slice(0, 20),
      });
    } catch (err) {
      const reason = err.name === 'TimeoutError' ? `timed out after ${config.serviceTimeoutMs} ms` : err.cause?.code || err.message;
      console.warn(`[orchestrator] ${component.name} failed: ${reason}`);
      Object.assign(result, { status: 'failed', errorMessages: [String(reason)] });
    }
    result.durationMs = Date.now() - started;
  }

  const statuses = run.components.map((c) => c.status);
  run.status = statuses.every((s) => s === 'ok') ? 'completed' : statuses.some((s) => s === 'ok') ? 'partial' : 'failed';
  run.finishedAt = new Date();
  await run.save();
  return run;
}
