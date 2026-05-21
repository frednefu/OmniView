import api from './index'

export function getResults(params) {
  return api.get('/results', { params }).then((r) => r.data)
}

export function getRoutes(params) {
  return api.get('/results/routes', { params }).then((r) => r.data)
}

export function getScanLogs(params) {
  return api.get('/scan-logs', { params }).then((r) => r.data)
}

export function getScanLog(id) {
  return api.get(`/scan-logs/${id}`).then((r) => r.data)
}
