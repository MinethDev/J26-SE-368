import 'dotenv/config';

const env = (name, fallback) => process.env[name] ?? fallback;

export const config = {
  port: Number(env('PORT', 4000)),
  mongoUri: env('MONGODB_URI', 'mongodb://127.0.0.1:27017/devintel'),
  jwtSecret: env('JWT_SECRET', 'dev-only-secret-change-me'),
  clientOrigin: env('CLIENT_ORIGIN', 'http://localhost:5173'),

  // Run order matters: later components receive earlier components' insights
  // as `upstream` (the intelligence flow). See docs/CONTRACTS.md.
  components: [
    { name: 'planning', url: env('PLANNING_SERVICE_URL', 'http://127.0.0.1:8001') },
    { name: 'sprint', url: env('SPRINT_SERVICE_URL', 'http://127.0.0.1:8002') },
    { name: 'quality', url: env('QUALITY_SERVICE_URL', 'http://127.0.0.1:8003') },
    { name: 'pull-request', url: env('PR_SERVICE_URL', 'http://127.0.0.1:8004') },
  ],
  serviceTimeoutMs: Number(env('SERVICE_TIMEOUT_MS', 60000)),

  github: { token: env('GITHUB_TOKEN', '') },
  jira: {
    baseUrl: env('JIRA_BASE_URL', ''),
    email: env('JIRA_EMAIL', ''),
    apiToken: env('JIRA_API_TOKEN', ''),
    storyPointsField: env('JIRA_STORY_POINTS_FIELD', 'customfield_10016'),
  },
  sonarqube: { url: env('SONARQUBE_URL', 'http://localhost:9000'), token: env('SONARQUBE_TOKEN', '') },
};

export const COMPONENT_NAMES = config.components.map((c) => c.name);
