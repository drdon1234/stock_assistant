async function request(path, options) {
  const response = await fetch(path, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`)
  return body
}

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
  addAttention: (code) => request(`/api/attention/${code}`, { method: 'PUT' }),
  removeAttention: (code) => request(`/api/attention/${code}`, { method: 'DELETE' }),
  search: (q) => request(`/api/search${query({ q })}`),
}
