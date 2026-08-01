import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const adminSidebarCollapsed = ref(false)

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function toggleAdminSidebar() {
    adminSidebarCollapsed.value = !adminSidebarCollapsed.value
  }

  return {
    sidebarCollapsed,
    adminSidebarCollapsed,
    toggleSidebar,
    toggleAdminSidebar,
  }
})
