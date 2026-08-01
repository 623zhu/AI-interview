import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/styles/variables.css'
import './assets/styles/main.css'


// 用户端拥有独立的 Vue 和 Pinia 实例，不与管理端共享运行时状态。
const app = createApp(App)

app.use(createPinia())
app.mount('#app')
