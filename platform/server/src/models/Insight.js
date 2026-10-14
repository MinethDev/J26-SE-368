// Contract 2: the Knowledge Repository. Every component's output is stored here in one
// shared format (shared/schemas/insight.schema.json), plus platform-managed fields.
import mongoose from 'mongoose';

const { Schema } = mongoose;

const insightSchema = new Schema(
  {
    // Platform-managed
    projectId: { type: String, required: true, index: true },
    runId: { type: Schema.Types.ObjectId, ref: 'AnalysisRun', index: true },
    feedback: {
      decision: { type: String, enum: ['accepted', 'rejected'] },
      comment: String,
      by: String,
      at: Date,
    },

    // From the component (validated against the JSON schema before saving)
    component: { type: String, required: true, index: true },
    type: { type: String, required: true },
    title: { type: String, required: true },
    target: { type: { type: String }, id: String, label: String },
    prediction: { label: String, value: Schema.Types.Mixed, unit: String },
    confidence: Number,
    severity: { type: String, enum: ['info', 'low', 'medium', 'high', 'critical'], default: 'info' },
    explanation: [{ _id: false, feature: String, value: Schema.Types.Mixed, impact: Number }],
    recommendations: [String],
    evidence: [{ _id: false, source: String, ref: String, note: String }],
    modelVersion: String,
    isStub: { type: Boolean, default: false },
  },
  { timestamps: true }
);

export const Insight = mongoose.model('Insight', insightSchema);
