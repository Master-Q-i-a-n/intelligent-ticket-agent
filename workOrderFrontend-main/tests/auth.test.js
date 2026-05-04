import assert from 'node:assert/strict'
import { getDefaultRouteByRole, normalizeRole } from '../src/utils/auth.js'

assert.equal(normalizeRole(undefined), 'guest')
assert.equal(normalizeRole('admin'), 'admin')
assert.equal(normalizeRole('USER'), 'user')

assert.equal(getDefaultRouteByRole('user'), '/feedback')
assert.equal(getDefaultRouteByRole('admin'), '/work-order')
assert.equal(getDefaultRouteByRole('guest'), '/login')
