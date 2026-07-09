import api from './index'

export function getTaskOverview() {
  return api.get('/task-overview').then(r => r.data)
}
