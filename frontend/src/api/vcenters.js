import api from './index'

export function getVCenters(params) {
  return api.get('/vcenters', { params }).then((r) => r.data)
}

export function getVCenter(id) {
  return api.get(`/vcenters/${id}`).then((r) => r.data)
}

export function createVCenter(data) {
  return api.post('/vcenters', data).then((r) => r.data)
}

export function updateVCenter(id, data) {
  return api.put(`/vcenters/${id}`, data).then((r) => r.data)
}

export function deleteVCenter(id) {
  return api.delete(`/vcenters/${id}`).then((r) => r.data)
}

export function triggerVCenterScan(id) {
  return api.post(`/vcenters/${id}/scan`).then((r) => r.data)
}

export function testVCenterConnection(data) {
  return api.post('/vcenters/test', data).then((r) => r.data)
}

export function scanAllVCenters() {
  return api.post('/vcenters/scan-all').then((r) => r.data)
}

export function deleteAllVCenters() {
  return api.delete('/vcenters/all').then((r) => r.data)
}

export function getVMInventory(params) {
  return api.get('/vcenters/vms', { params }).then((r) => r.data)
}

export function getVCenterVMs(id, params) {
  return api.get(`/vcenters/${id}/vms`, { params }).then((r) => r.data)
}
