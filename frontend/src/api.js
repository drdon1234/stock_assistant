let onUnauthorized = () => {}

// 登录失效（凭证过期、被吊销或密码已修改）时回到登录页
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

async function request(path, options = {}) {
  // X-Requested-With 是后端的 CSRF 校验：跨站页面无法附带自定义请求头
  const headers = { 'X-Requested-With': 'instock', ...(options.body ? { 'Content-Type': 'application/json' } : {}) }
  const response = await fetch(path, { ...options, headers })
  const body = await response.json().catch(() => ({}))
  if (response.status === 401) onUnauthorized()
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`)
  return body
}

const send = (method, path, data) => request(path, { method, body: data === undefined ? undefined : JSON.stringify(data) })

const query = (params) => {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return entries.length ? `?${new URLSearchParams(entries)}` : ''
}

export const api = {
  meta: () => request('/api/meta'),
  overview: () => request('/api/overview'),
  table: (name, date) => request(`/api/tables/${name}${query({ date })}`),
  signals: (date, strategy) => request(`/api/signals${query({ date, strategy })}`),
  backtest: () => request('/api/backtest'),
  kline: (code) => request(`/api/kline/${code}`),
  attention: () => request('/api/attention'),
  addAttention: (code) => send('PUT', `/api/attention/${code}`),
  removeAttention: (code) => send('DELETE', `/api/attention/${code}`),
  search: (q) => request(`/api/search${query({ q })}`),
  session: () => request('/api/auth/session'),
  login: (username, password) => send('POST', '/api/auth/session', { username, password }),
  logout: () => send('DELETE', '/api/auth/session'),
  changePassword: (old, password) => send('POST', '/api/auth/password', { old, new: password }),
  users: () => request('/api/users'),
  createUser: (data) => send('POST', '/api/users', data),
  updateUser: (name, data) => send('PUT', `/api/users/${name}`, data),
  deleteUser: (name) => send('DELETE', `/api/users/${name}`),
  quantStatus: () => request('/api/quant/status'),
  quantCheck: (code) => send('POST', '/api/quant/check', { code }),
  quantJobs: () => request('/api/quant/jobs'),
  quantJob: (id) => request(`/api/quant/jobs/${id}`),
  quantSubmit: (data) => send('POST', '/api/quant/jobs', data),
  quantRemove: (id) => send('DELETE', `/api/quant/jobs/${id}`),
}
