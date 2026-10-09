import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'
import './model-management.css'
import './model-management-list.css'
createApp(App).use(router).mount('#app')
