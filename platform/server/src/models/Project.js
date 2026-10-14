import mongoose from 'mongoose';

// A DevIntel project links one GitHub repo, one Jira board and one SonarQube project.
const projectSchema = new mongoose.Schema(
  {
    key: { type: String, required: true, unique: true, trim: true }, // used as projectId everywhere
    name: { type: String, required: true },
    description: String,
    github: { owner: String, repo: String },
    jira: { boardId: Number },
    sonarqube: { projectKey: String },
    lastSync: { github: Date, jira: Date, sonarqube: Date, upload: Date },
  },
  { timestamps: true }
);

export const Project = mongoose.model('Project', projectSchema);
