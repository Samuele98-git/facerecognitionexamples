import React, { createContext, useContext, useEffect, useState } from 'react'
import { api, setUnauthorizedHandler } from './api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  // undefined = still checking session, null = logged out, object = logged in
  const [user, setUser] = useState(undefined)

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null)) // any 401 anywhere -> back to login
    api.auth.me().then(setUser).catch(() => setUser(null))
  }, [])

  const login = async (username, password) => {
    await api.auth.login(username, password)
    const me = await api.auth.me()
    setUser(me)
    return me
  }

  const logout = async () => {
    try {
      await api.auth.logout()
    } catch {
      /* ignore */
    }
    setUser(null)
  }

  return <AuthCtx.Provider value={{ user, login, logout }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
