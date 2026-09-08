import React, { useState } from 'react'
import { useAuth } from './auth'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(username.trim(), password)
    } catch (err) {
      setError(err.message || 'Sign-in failed')
      setBusy(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-aurora" />
      <div className="login-grid" />
      <form className="login-card" onSubmit={submit}>
        <div className="login-mark">◉</div>
        <h1 className="login-title">
          FACE<span className="accent">ACCESS</span>
        </h1>
        <p className="login-sub">Secure biometric access control</p>

        <label className="field">
          <span>Username</span>
          <input
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            placeholder="admin"
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            placeholder="••••••••"
          />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button className="login-btn" type="submit" disabled={busy || !username || !password}>
          {busy ? 'Authenticating…' : 'Sign in'}
        </button>

        <div className="login-foot">
          <span className="dot ok" /> On-premises · offline · encrypted
        </div>
      </form>
    </div>
  )
}
