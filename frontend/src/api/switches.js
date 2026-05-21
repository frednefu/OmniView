import api from './index'

export function getSwitches(params) {
  return api.get('/switches', { params }).then((r) => r.data)
}

export function getSwitch(id) {
  return api.get(`/switches/${id}`).then((r) => r.data)
}

export function createSwitch(data) {
  return api.post('/switches', data).then((r) => r.data)
}

export function updateSwitch(id, data) {
  return api.put(`/switches/${id}`, data).then((r) => r.data)
}

export function deleteSwitch(id) {
  return api.delete(`/switches/${id}`).then((r) => r.data)
}

export function triggerScan(id) {
  return api.post(`/switches/${id}/scan`).then((r) => r.data)
}
