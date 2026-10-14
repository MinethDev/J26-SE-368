import mongoose from 'mongoose';

// Role-based access: managers can run analyses and sync data sources,
// developers can view insights and give feedback.
export const ROLES = ['developer', 'manager'];

const userSchema = new mongoose.Schema(
  {
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    name: { type: String, required: true },
    passwordHash: { type: String, required: true },
    role: { type: String, enum: ROLES, default: 'developer' },
  },
  { timestamps: true }
);

userSchema.methods.toSafeJSON = function toSafeJSON() {
  return { id: this._id.toString(), email: this.email, name: this.name, role: this.role };
};

export const User = mongoose.model('User', userSchema);
