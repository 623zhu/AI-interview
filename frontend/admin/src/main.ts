import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/styles/variables.css'
import './assets/styles/main.css'


// 管理端从 admin.html 启动，拥有独立于候选人端的应用实例。
const app = createApp(App)

app.use(createPinia())
app.mount('#app')
