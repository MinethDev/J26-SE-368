import { config } from './config.js';
import { connectDb } from './db.js';
import { createApp } from './app.js';

try {
  await connectDb();
} catch (err) {
  console.error(`[db] could not connect to MongoDB at ${config.mongoUri}: ${err.message}`);
  console.error('      Is MongoDB running? Try: docker compose up -d mongo');
  process.exit(1);
}

createApp().listen(config.port, () => {
  console.log(`[server] DevIntel API listening on http://localhost:${config.port}`);
});
