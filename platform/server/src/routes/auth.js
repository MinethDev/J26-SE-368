import { Router } from 'express';
import bcrypt from 'bcryptjs';
import { User, ROLES } from '../models/index.js';
import { requireAuth, requireRole, signToken } from '../middleware/auth.js';
import { asyncHandler, HttpError } from '../middleware/errors.js';

const router = Router();

router.post(
  '/login',
  asyncHandler(async (req, res) => {
    const { email, password } = req.body || {};
    if (!email || !password) throw new HttpError(400, 'Email and password are required');
    const user = await User.findOne({ email: String(email).toLowerCase() });
    if (!user || !(await bcrypt.compare(password, user.passwordHash))) throw new HttpError(401, 'Incorrect email or password');
    res.json({ token: signToken(user), user: user.toSafeJSON() });
  })
);

router.get('/me', requireAuth, (req, res) => {
  res.json({ user: { id: req.user.sub, email: req.user.email, name: req.user.name, role: req.user.role } });
});

// Managers create accounts for their team (no public sign-up).
router.post(
  '/users',
  requireAuth,
  requireRole('manager'),
  asyncHandler(async (req, res) => {
    const { email, name, password, role = 'developer' } = req.body || {};
    if (!email || !name || !password) throw new HttpError(400, 'email, name and password are required');
    if (password.length < 8) throw new HttpError(400, 'Password must be at least 8 characters');
    if (!ROLES.includes(role)) throw new HttpError(400, `role must be one of: ${ROLES.join(', ')}`);
    if (await User.exists({ email: email.toLowerCase() })) throw new HttpError(409, 'A user with this email already exists');
    const user = await User.create({ email, name, role, passwordHash: await bcrypt.hash(password, 10) });
    res.status(201).json({ user: user.toSafeJSON() });
  })
);

export default router;
