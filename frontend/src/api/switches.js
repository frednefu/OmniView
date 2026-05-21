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

export function testSwitchConnection(data) {
  return api.post('/switches/test', data).then((r) => r.data)
}

export function importSwitches(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/switches/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((r) => r.data)
}

export function downloadTemplate() {
  return api.get('/switches/template', { responseType: 'blob' }).then((r) => {
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'switch_import_template.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  })
}

export function scanAllSwitches() {
  return api.post('/switches/scan-all').then((r) => r.data)
}

export function deleteAllSwitches() {
  return api.delete('/switches/all').then((r) => r.data)
}
