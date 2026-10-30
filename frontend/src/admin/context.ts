import { createContext, useContext } from 'react'
import type { Admin } from './api'

export const AdminContext = createContext<{
  user: Admin | null
  call: <T>(work: () => Promise<T>) => Promise<T>
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
} | null>(null)

export function useAdmin() {
  const value = useContext(AdminContext)
  if (!value) throw new Error('AdminProvider ausente')
  return value
}
