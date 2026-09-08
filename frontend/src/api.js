// REST client. Every request carries the session cookie (credentials:'include'); a 401
// triggers the registered handler so the app drops back to the login screen automatically.
const JSON_HEADERS = { 'Content-Type': 'application/json' }

let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

async function ok(res) {
  if (res.status === 401 && onUnauthorized) onUnauthorized()
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      /* non-JSON body */
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}

const req = (extra = {}) => ({ credentials: 'include', ...extra })

export const api = {
  ping: () => fetch('/api/ping').then(ok),
  health: () => fetch('/api/health', req()).then(ok),

  auth: {
    me: () => fetch('/api/auth/me', req()).then(ok),
    login: (username, password) =>
      fetch('/api/auth/login', req({ method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ username, password }) })).then(ok),
    logout: () => fetch('/api/auth/logout', req({ method: 'POST' })).then(ok),
    users: {
      list: () => fetch('/api/auth/users', req()).then(ok),
      create: (b) => fetch('/api/auth/users', req({ method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(b) })).then(ok),
      update: (id, b) => fetch(`/api/auth/users/${id}`, req({ method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify(b) })).then(ok),
      remove: (id) => fetch(`/api/auth/users/${id}`, req({ method: 'DELETE' })).then(ok),
    },
  },

  settings: {
    get: () => fetch('/api/settings', req()).then(ok),
    update: (b) => fetch('/api/settings', req({ method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify(b) })).then(ok),
  },

  people: {
    list: () => fetch('/api/people', req()).then(ok),
    create: (b) => fetch('/api/people', req({ method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(b) })).then(ok),
    update: (id, b) => fetch(`/api/people/${id}`, req({ method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify(b) })).then(ok),
    remove: (id) => fetch(`/api/people/${id}`, req({ method: 'DELETE' })).then(ok),
    addPhoto: (id, file) => {
      const fd = new FormData()
      fd.append('file', file)
      return fetch(`/api/people/${id}/photos`, req({ method: 'POST', body: fd })).then(ok)
    },
    removePhoto: (id, photoId) => fetch(`/api/people/${id}/photos/${photoId}`, req({ method: 'DELETE' })).then(ok),
  },

  cameras: {
    list: () => fetch('/api/cameras', req()).then(ok),
    create: (b) => fetch('/api/cameras', req({ method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(b) })).then(ok),
    update: (id, b) => fetch(`/api/cameras/${id}`, req({ method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify(b) })).then(ok),
    remove: (id) => fetch(`/api/cameras/${id}`, req({ method: 'DELETE' })).then(ok),
  },

  events: {
    list: (query = '') => fetch(`/api/events${query}`, req()).then(ok),
  },
}
