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
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      router.push('/login')
      ElMessage.error('登录已过期，请重新登录')
      return Promise.reject(err)
    }
    // 网络错误（无响应）才在这里弹窗，业务错误交给调用方处理
    if (!err.response) {
      ElMessage.error('网络连接失败，请检查网络')
      return Promise.reject(err)
    }
    // 500 服务端错误统一提示（调用方可能没有专门的错误处理）
    if (err.response.status >= 500) {
      const detail = err.response?.data?.detail
      ElMessage.error(typeof detail === 'string' ? detail : '服务器内部错误，请稍后重试')
      return Promise.reject(err)
    }
    // 4xx 错误交给业务 catch 处理（含 detail 的错误），不在此弹窗
    return Promise.reject(err)
  },
)

export default api
