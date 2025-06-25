import React, { createContext, useContext, useEffect, useState } from 'react'
import { apiClient } from '../lib/api'

interface User {
  id: string
  email: string
  organization: {
    id: string
    name: string
  }
  permissions: string[]
  verified: boolean
}

interface AuthContextType {
  user: User | null
  token: string | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshToken: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(localStorage.getItem('lemma_token'))
  const [isLoading, setIsLoading] = useState(true)

  // Check if user is authenticated
  const isAuthenticated = Boolean(user && token)

  // Initialize auth state
  useEffect(() => {
    const initAuth = async () => {
      try {
        // Check if we have a token in localStorage
        const storedToken = localStorage.getItem('lemma_token')
        if (storedToken) {
          setToken(storedToken)
          apiClient.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`
          
          // Try to get current user data
          const response = await apiClient.get('/api/v2/auth/me')
          if (response.data.success) {
            setUser(response.data.user)
          } else {
            // Token is invalid, clear it
            localStorage.removeItem('lemma_token')
            setToken(null)
          }
        } else {
          // No token in localStorage, check if Flask session exists
          try {
            const sessionResponse = await apiClient.post('/api/v2/auth/session-token')
            if (sessionResponse.data.success) {
              const newToken = sessionResponse.data.token
              setToken(newToken)
              localStorage.setItem('lemma_token', newToken)
              apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`
              
              // Get user data
              const userResponse = await apiClient.get('/api/v2/auth/me')
              if (userResponse.data.success) {
                setUser(userResponse.data.user)
              }
            }
          } catch (error) {
            // No Flask session either, user needs to log in
            console.log('No existing session found')
          }
        }
      } catch (error) {
        console.error('Auth initialization error:', error)
        // Clear invalid token
        localStorage.removeItem('lemma_token')
        setToken(null)
        setUser(null)
      } finally {
        setIsLoading(false)
      }
    }

    initAuth()
  }, [])

  const login = async (email: string, password: string) => {
    try {
      // This would typically go to your Flask login endpoint
      // For now, we'll simulate a successful login
      const loginResponse = await fetch('/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      })

      if (loginResponse.ok) {
        // After successful Flask login, get the JWT token
        const sessionResponse = await apiClient.post('/api/v2/auth/session-token')
        if (sessionResponse.data.success) {
          const newToken = sessionResponse.data.token
          setToken(newToken)
          localStorage.setItem('lemma_token', newToken)
          apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`
          
          // Get user data
          const userResponse = await apiClient.get('/api/v2/auth/me')
          if (userResponse.data.success) {
            setUser(userResponse.data.user)
          }
        }
      } else {
        throw new Error('Login failed')
      }
    } catch (error) {
      console.error('Login error:', error)
      throw error
    }
  }

  const logout = async () => {
    try {
      // Clear React state
      setUser(null)
      setToken(null)
      localStorage.removeItem('lemma_token')
      delete apiClient.defaults.headers.common['Authorization']
      
      // Also logout from Flask session
      await fetch('/logout', { method: 'POST' })
      
      // Redirect to home page
      window.location.href = '/'
    } catch (error) {
      console.error('Logout error:', error)
      // Even if Flask logout fails, clear local state
      window.location.href = '/'
    }
  }

  const refreshToken = async () => {
    try {
      const response = await apiClient.post('/api/v2/auth/refresh')
      if (response.data.success) {
        // Token refreshed successfully
        console.log('Token refreshed')
      }
    } catch (error) {
      console.error('Token refresh error:', error)
      // If refresh fails, logout user
      logout()
    }
  }

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    isAuthenticated,
    login,
    logout,
    refreshToken,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
} 