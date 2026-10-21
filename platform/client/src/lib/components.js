// Display metadata for the four intelligence components.
export const COMPONENTS = [
  {
    key: 'planning',
    path: '/planning',
    name: 'Project Planning',
    owner: 'Vidusini W. M. O.',
    summary: 'Effort, priority, timeline and resource recommendations from requirements and history.',
  },
  {
    key: 'sprint',
    path: '/sprint',
    name: 'Sprint',
    owner: 'Wahalathanthri E. I.',
    summary: 'Sprint health, delay risk, workload and bottleneck interventions.',
  },
  {
    key: 'quality',
    path: '/quality',
    name: 'Software Quality',
    owner: 'Senura Virantha S.J.',
    summary: 'Quality-risk hotspots, explanations and corrective actions from SonarQube and GitHub.',
  },
  {
    key: 'pull-request',
    path: '/pull-requests',
    name: 'Pull Request',
    owner: 'Perera W. M. M.',
    summary: 'Recommended reviewers, AI code review and merge readiness for every open pull request.',
  },
];

export const componentByKey = Object.fromEntries(COMPONENTS.map((c) => [c.key, c]));
