import React, { useEffect, useState } from 'react'
import { api } from './api'
import { useAuth } from './auth'

export default function Settings() {
  const { user } = useAuth()
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.settings.get().then(setS).catch((e) => setErr(e.message))
  }, [])

  if (!s) return <div className="panel"><div className="empty">Loading settings…</div></div>

  const save = async () => {
    setMsg('')
    setErr('')
    try {
      const updated = await api.settings.update({
        recognition_threshold: Number(s.recognition_threshold),
        access_webhook_url: s.access_webhook_url,
        log_unknown: s.log_unknown,
        liveness_enabled: s.liveness_enabled,
        liveness_threshold: Number(s.liveness_threshold),
      })
      setS(updated)
      setMsg('Settings saved')
      setTimeout(() => setMsg(''), 2500)
    } catch (e) {
      setErr(e.message)
    }
  }

  const t = Number(s.recognition_threshold)

  return (
    <div className="panel settings">
      <section className="card">
        <h2>Recognition</h2>
        <div className="slider-row">
          <div className="slider-head">
            <span>Match threshold</span>
            <span className="threshold-val">{t.toFixed(2)}</span>
          </div>
          <input
            type="range" min="0.30" max="0.70" step="0.01"
            value={s.recognition_threshold}
            onChange={(e) => setS({ ...s, recognition_threshold: e.target.value })}
          />
          <div className="slider-scale"><span>lenient</span><span>0.45 recommended</span><span>strict</span></div>
          <p className="hint">Higher = fewer false accepts (safer for a door), but more false rejects.</p>
        </div>
        <label className="check">
          <input type="checkbox" checked={s.log_unknown} onChange={(e) => setS({ ...s, log_unknown: e.target.checked })} />
          <span>Log unknown faces as alerts</span>
        </label>
      </section>

      <section className="card">
        <h2>Liveness / anti-spoofing</h2>
        <label className="check">
          <input type="checkbox" checked={s.liveness_enabled} onChange={(e) => setS({ ...s, liveness_enabled: e.target.checked })} />
          <span>Require liveness — reject printed photos &amp; phone/tablet screens</span>
        </label>
        <div className="slider-row" style={{ marginTop: 14, opacity: s.liveness_enabled ? 1 : 0.5 }}>
          <div className="slider-head">
            <span>Liveness threshold</span>
            <span className="threshold-val">{Number(s.liveness_threshold).toFixed(2)}</span>
          </div>
          <input
            type="range" min="0.30" max="0.95" step="0.01"
            value={s.liveness_threshold}
            disabled={!s.liveness_enabled}
            onChange={(e) => setS({ ...s, liveness_threshold: e.target.value })}
          />
          <p className="hint">Higher = stricter. MiniFASNet, runs 100% offline. Tune with real vs. photo tests from your own cameras.</p>
        </div>
      </section>

      <section className="card">
        <h2>Door relay / webhook</h2>
        <p className="hint">
          POSTed on every <b>granted</b> access. Point it at a relay on your LAN
          (e.g. <code>http://192.168.1.30/relay/on</code>). Leave blank to disable. Stays on-premises.
        </p>
        <input
          className="wide"
          placeholder="http://…"
          value={s.access_webhook_url}
          onChange={(e) => setS({ ...s, access_webhook_url: e.target.value })}
        />
      </section>

      <div className="settings-actions">
        <button className="primary" onClick={save}>Save settings</button>
        {msg && <span className="ok-msg">✓ {msg}</span>}
        {err && <span className="err-msg">{err}</span>}
      </div>

      <UsersCard meId={user?.id} />
    </div>
  )
}

function UsersCard({ meId }) {
  const [users, setUsers] = useState([])
  const [form, setForm] = useState({ username: '', password: '', role: 'operator' })
  const [err, setErr] = useState('')

  const reload = () => api.auth.users.list().then(setUsers).catch((e) => setErr(e.message))
  useEffect(() => { reload() }, [])

  const create = async (e) => {
    e.preventDefault()
    setErr('')
    try {
      await api.auth.users.create(form)
      setForm({ username: '', password: '', role: 'operator' })
      reload()
    } catch (ex) {
      setErr(ex.message)
    }
  }

  const act = (p) => p.then(reload).catch((ex) => setErr(ex.message))

  return (
    <section className="card">
      <h2>Users &amp; access</h2>
      <form className="user-form" onSubmit={create}>
        <input placeholder="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input type="password" placeholder="password (min 8)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="operator">operator</option>
          <option value="admin">admin</option>
        </select>
        <button className="primary" type="submit">Add user</button>
      </form>
      {err && <div className="err-msg">{err}</div>}

      <table className="user-table">
        <thead>
          <tr><th>User</th><th>Role</th><th>Status</th><th>Last login</th><th></th></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className={u.active ? '' : 'inactive'}>
              <td>{u.username}{u.id === meId && <span className="you"> (you)</span>}</td>
              <td>
                <select
                  value={u.role}
                  disabled={u.id === meId}
                  onChange={(e) => act(api.auth.users.update(u.id, { role: e.target.value }))}
                >
                  <option value="operator">operator</option>
                  <option value="admin">admin</option>
                </select>
              </td>
              <td>{u.active ? <span className="badge granted">active</span> : <span className="badge denied">disabled</span>}</td>
              <td className="muted">{u.last_login ? new Date(u.last_login).toLocaleString() : '—'}</td>
              <td className="row-actions">
                <button onClick={() => { const p = prompt(`New password for ${u.username} (min 8 chars):`); if (p) act(api.auth.users.update(u.id, { password: p })) }}>Reset pw</button>
                {u.id !== meId && (
                  <>
                    <button onClick={() => act(api.auth.users.update(u.id, { active: !u.active }))}>{u.active ? 'Disable' : 'Enable'}</button>
                    <button className="danger" onClick={() => { if (confirm(`Delete user ${u.username}?`)) act(api.auth.users.remove(u.id)) }}>Delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
