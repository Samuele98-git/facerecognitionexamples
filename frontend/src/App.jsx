import React, { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { AuthProvider, useAuth } from './auth'
import Login from './Login'
import Settings from './Settings'

export default function App() {
  return (
    <AuthProvider>
      <Root />
    </AuthProvider>
  )
}

function Root() {
  const { user } = useAuth()
  if (user === undefined) {
    return <div className="splash"><span className="login-mark spin">◉</span></div>
  }
  if (!user) return <Login />
  return <Shell />
}

// --- helpers --------------------------------------------------------------
function useInterval(callback, ms) {
  const saved = useRef(callback)
  saved.current = callback
  useEffect(() => {
    const id = setInterval(() => saved.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

function Shell() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState('dashboard')
  const [health, setHealth] = useState(null)

  const tabs = [
    ['dashboard', 'Dashboard'],
    ['people', 'People'],
    ['cameras', 'Cameras'],
  ]
  if (user.role === 'admin') tabs.push(['settings', 'Settings'])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [tab])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◉</span> FACE<span className="accent">ACCESS</span>
        </div>
        <nav>
          {tabs.map(([id, label]) => (
            <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          {health && (
            <span className="health">
              <span className={`dot ${health.model_ready ? 'ok' : 'bad'}`} />
              {health.people}p · {health.enrolled_faces}f · thr {health.threshold} · {health.gpu ? 'GPU' : 'CPU'}
            </span>
          )}
          <div className="user-chip">
            <span className="avatar">{user.username.slice(0, 1).toUpperCase()}</span>
            <span className="user-meta">
              <span className="user-name">{user.username}</span>
              <span className="user-role">{user.role}</span>
            </span>
            <button className="logout" onClick={logout} title="Sign out">⏻</button>
          </div>
        </div>
      </header>

      <main>
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'people' && <People />}
        {tab === 'cameras' && <Cameras />}
        {tab === 'settings' && user.role === 'admin' && <Settings />}
      </main>
    </div>
  )
}

// --- Dashboard ------------------------------------------------------------
function Dashboard() {
  const [cams, setCams] = useState([])
  const [events, setEvents] = useState([])
  const [activeCam, setActiveCam] = useState(null)

  useEffect(() => {
    api.cameras.list().then(setCams).catch(() => {})
  }, [])
  useInterval(() => api.events.list('?limit=40').then(setEvents).catch(() => {}), 2500)

  const enabled = cams.filter((c) => c.enabled)

  return (
    <div className="dashboard">
      <section className="grid-section">
        <h2>Live cameras <span className="count">{enabled.length}</span></h2>
        {enabled.length === 0 && <div className="empty">No enabled cameras yet. Add one in the Cameras tab.</div>}
        <div className="camera-grid">
          {enabled.map((c) => (
            <div className="cam-tile" key={c.id} onClick={() => setActiveCam(c)} title="Click to view fullscreen">
              <img
                src={`/api/cameras/${c.id}/stream?t=${c.id}`}
                alt={c.name}
                onError={(e) => e.currentTarget.classList.add('broken')}
              />
              <div className="cam-scan" />
              <div className="cam-expand">⤢</div>
              <div className="cam-label">
                <span className="dot ok" /> {c.name}{c.location ? ` · ${c.location}` : ''}
              </div>
            </div>
          ))}
        </div>
      </section>

      <aside className="events">
        <h2>Recognition feed</h2>
        <div className="event-list">
          {events.length === 0 && <div className="empty small">No activity yet.</div>}
          {events.map((ev) => (
            <div className={`event ${ev.decision}`} key={ev.id}>
              {ev.snapshot ? <img src={`/api/media/snapshots/${ev.snapshot}`} alt="" /> : <div className="event-noimg">?</div>}
              <div className="ev-body">
                <div className="ev-name">{ev.person_name || 'Unknown face'}</div>
                <div className="ev-meta">
                  <span className={`badge ${ev.decision}`}>{ev.decision}</span>
                  {ev.similarity != null && <span>{(ev.similarity * 100).toFixed(0)}%</span>}
                  <span className="time">{new Date(ev.created_at).toLocaleTimeString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {activeCam && <CameraModal cam={activeCam} onClose={() => setActiveCam(null)} />}
    </div>
  )
}

// --- Fullscreen camera view -----------------------------------------------
function CameraModal({ cam, onClose }) {
  const boxRef = useRef(null)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const toggleNative = (e) => {
    e.stopPropagation()
    const el = boxRef.current
    if (!el) return
    if (document.fullscreenElement) document.exitFullscreen?.()
    else el.requestFullscreen?.().catch(() => {})
  }

  return (
    <div className="cam-modal" onClick={onClose}>
      <div className="cam-modal-inner" ref={boxRef} onClick={(e) => e.stopPropagation()}>
        <div className="cam-modal-bar">
          <span className="cam-modal-title">
            <span className="dot ok" /> {cam.name}{cam.location ? ` · ${cam.location}` : ''}
          </span>
          <div className="cam-modal-actions">
            <button onClick={toggleNative} title="Toggle true fullscreen">⤢</button>
            <button onClick={onClose} title="Close (Esc)">✕</button>
          </div>
        </div>
        <img
          className="cam-modal-img"
          src={`/api/cameras/${cam.id}/stream?view=full`}
          alt={cam.name}
          onError={(e) => e.currentTarget.classList.add('broken')}
        />
      </div>
    </div>
  )
}

// --- People / enrollment --------------------------------------------------
function People() {
  const [people, setPeople] = useState([])
  const [form, setForm] = useState({ name: '', employee_id: '', role: '' })
  const [error, setError] = useState('')

  const reload = () => api.people.list().then(setPeople).catch((e) => setError(e.message))
  useEffect(() => { reload() }, [])

  const create = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    try {
      await api.people.create(form)
      setForm({ name: '', employee_id: '', role: '' })
      reload()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="panel">
      <div className="card panel-form">
        <h2>Add person</h2>
        <form onSubmit={create}>
          <input placeholder="Full name *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="Employee ID" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} />
          <input placeholder="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} />
          <button className="primary" type="submit">Add person</button>
        </form>
        <p className="hint">Then upload <b>3–5 photos per person</b> from different angles (front, ¾ left/right) for reliable recognition.</p>
      </div>

      {error && <div className="error" onClick={() => setError('')}>{error} (click to dismiss)</div>}

      <div className="people-list">
        {people.length === 0 && <div className="empty">No people enrolled yet.</div>}
        {people.map((p) => <PersonCard key={p.id} person={p} reload={reload} onError={setError} />)}
      </div>
    </div>
  )
}

function PersonCard({ person, reload, onError }) {
  const fileRef = useRef()

  const upload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    try {
      await api.people.addPhoto(person.id, file)
      reload()
    } catch (err) {
      onError(err.message)
    }
    e.target.value = ''
  }

  return (
    <div className={`card person-card ${person.active ? '' : 'inactive'}`}>
      <div className="person-head">
        <div>
          <div className="person-name">{person.name}</div>
          <div className="person-sub">{person.role || '—'}{person.employee_id ? ` · #${person.employee_id}` : ''}</div>
        </div>
        <div className="person-actions">
          <button
            className={person.active ? 'toggle on' : 'toggle off'}
            onClick={() => api.people.update(person.id, { active: !person.active }).then(reload).catch((e) => onError(e.message))}
          >
            {person.active ? 'Active' : 'Inactive'}
          </button>
          <button className="danger" onClick={() => { if (confirm(`Delete ${person.name}?`)) api.people.remove(person.id).then(reload).catch((e) => onError(e.message)) }}>Delete</button>
        </div>
      </div>
      <div className="photos">
        {person.photos.map((ph) => (
          <div className="photo" key={ph.id}>
            <img src={`/api/media/uploads/${ph.filename}`} alt="" />
            <button title="remove" onClick={() => api.people.removePhoto(person.id, ph.id).then(reload).catch((e) => onError(e.message))}>×</button>
          </div>
        ))}
        <button className="add-photo" onClick={() => fileRef.current.click()}>+ photo</button>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={upload} />
      </div>
      {person.photos.length === 0 && <div className="warn">⚠ No photos — can't be recognized yet.</div>}
    </div>
  )
}

// --- Cameras --------------------------------------------------------------
function Cameras() {
  const [cams, setCams] = useState([])
  const [form, setForm] = useState({ name: '', rtsp_url: '', location: '' })
  const [error, setError] = useState('')

  const reload = () => api.cameras.list().then(setCams).catch((e) => setError(e.message))
  useEffect(() => { reload() }, [])

  const create = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.rtsp_url.trim()) return
    try {
      await api.cameras.create({ ...form, enabled: true })
      setForm({ name: '', rtsp_url: '', location: '' })
      reload()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="panel">
      <div className="card panel-form">
        <h2>Add camera</h2>
        <form onSubmit={create}>
          <input placeholder="Name * e.g. Main entrance" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="wide" placeholder="RTSP URL * e.g. rtsp://user:pass@192.168.1.50:554/Streaming/Channels/101" value={form.rtsp_url} onChange={(e) => setForm({ ...form, rtsp_url: e.target.value })} />
          <input placeholder="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
          <button className="primary" type="submit">Add camera</button>
        </form>
        <p className="hint">Most IP cameras expose an <b>RTSP</b> URL (see the camera's ONVIF page). A local video-file path also works for testing.</p>
      </div>

      {error && <div className="error" onClick={() => setError('')}>{error} (click to dismiss)</div>}

      <div className="cameras-list">
        {cams.length === 0 && <div className="empty">No cameras configured.</div>}
        {cams.map((c) => (
          <div className={`card camera-row ${c.enabled ? '' : 'off'}`} key={c.id}>
            <div className="camera-info">
              <div className="cam-name"><span className={`dot ${c.enabled ? 'ok' : 'bad'}`} /> {c.name}</div>
              <div className="cam-url">{c.location || '—'} · <code>{c.rtsp_url}</code></div>
            </div>
            <div className="cam-actions">
              <button onClick={() => api.cameras.update(c.id, { enabled: !c.enabled }).then(reload)}>{c.enabled ? 'Disable' : 'Enable'}</button>
              <button className="danger" onClick={() => { if (confirm(`Delete camera ${c.name}?`)) api.cameras.remove(c.id).then(reload) }}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
