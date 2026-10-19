import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import mongoose from 'mongoose';
import { config } from './config.js';
import { requireAuth } from './middleware/auth.js';
import { errorHandler } from './middleware/errors.js';
import authRoutes from './routes/auth.js';
import projectRoutes from './routes/projects.js';
import insightRoutes from './routes/insights.js';
import orchestratorRoutes from './routes/orchestrator.js';

export function createApp() {
  const app = express();
  app.use(cors({ origin: config.clientOrigin }));
  app.use(express.json({ limit: '2mb' }));
  if (process.env.NODE_ENV !== 'test') app.use(morgan('dev')); // request log (audit trail)

  app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', service: 'devintel-server', database: mongoose.connection.readyState === 1 ? 'connected' : 'disconnected' });
  });

  app.use('/api/auth', authRoutes);
  app.use('/api/projects', requireAuth, projectRoutes);
  app.use('/api/insights', requireAuth, insightRoutes);
  app.use('/api/orchestrator', requireAuth, orchestratorRoutes);

  app.use('/api', (req, res) => res.status(404).json({ error: `No route ${req.method} ${req.originalUrl}` }));
  app.use(errorHandler);
  return app;
}
