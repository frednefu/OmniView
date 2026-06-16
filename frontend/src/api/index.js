import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => {
    // 检测被 WAF/nginx 拦截的 HTML 响应（HTTP 200 但 body 是 HTML）
    const data = res.data
    if (typeof data === 'string' && /^\s*</.test(data)) {
      // 尝试从 HTML 中提取错误信息
      let msg = '请求被拦截'
      const titleMatch = data.match(/<title>(.*?)<\/title>/i)
      if (titleMatch) msg = titleMatch[1]
      // 也尝试提取 body 文本
      const bodyMatch = data.match(/<body[^>]*>(.*?)<\/body>/is)
      if (bodyMatch) {
        const text = bodyMatch[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
        if (text && text.length < 200) msg += ': ' + text
      }
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
    return res
  },
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      router.push('/login')
      ElMessage.error('登录已过期，请重新登录')
      return Promise.reject(err)
    }
    // 网络错误（无响应）
    if (!err.response) {
      ElMessage.error('网络连接失败，请检查网络')
      return Promise.reject(err)
    }
    // 500 服务端错误统一提示
    if (err.response.status >= 500) {
      const detail = err.response?.data?.detail
      ElMessage.error(typeof detail === 'string' ? detail : '服务器内部错误，请稍后重试')
      return Promise.reject(err)
    }
    // 4xx 错误交给业务 catch 处理
    return Promise.reject(err)
  },
)

export default api
