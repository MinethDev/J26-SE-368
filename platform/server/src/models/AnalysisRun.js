import mongoose from 'mongoose';

// One orchestrator run across all components, with per-component status,
// so the dashboard can show what ran, what failed and why.
const componentResultSchema = new mongoose.Schema(
  {
    component: String,
    status: { type: String, enum: ['pending', 'ok', 'failed', 'skipped'], default: 'pending' },
    modelVersion: String,
    insightCount: { type: Number, default: 0 },
    rejectedCount: { type: Number, default: 0 },
    errorMessages: [String],
    durationMs: Number,
  },
  { _id: false }
);

const analysisRunSchema = new mongoose.Schema(
  {
    projectId: { type: String, required: true, index: true },
    triggeredBy: String,
    status: { type: String, enum: ['running', 'completed', 'partial', 'failed'], default: 'running' },
    components: [componentResultSchema],
    startedAt: Date,
    finishedAt: Date,
  },
  { timestamps: true }
);

export const AnalysisRun = mongoose.model('AnalysisRun', analysisRunSchema);
