import api from './index'

export function getAssetTree() {
  return api.get('/assets/tree').then((r) => r.data)
}

export function getDeptVMs(deptId, params = {}) {
  return api.get(`/assets/departments/${deptId}/vms`, { params }).then((r) => r.data)
}

export function getDeptDomains(deptId, params = {}) {
  return api.get(`/assets/departments/${deptId}/domains`, { params }).then((r) => r.data)
}

export function searchAssets(keyword) {
  return api.get('/assets/search', { params: { keyword } }).then((r) => r.data)
}

export function previewAutoMatch() {
  return api.get('/assets/auto-match/preview').then((r) => r.data)
}

export function executeAutoMatch() {
  return api.post('/assets/auto-match').then((r) => r.data)
}

export function matchOwner() {
  return api.post('/assets/auto-match/match-owner').then((r) => r.data)
}

export function startMatchOwner() {
  return api.post('/assets/auto-match/start-owner').then((r) => r.data)
}

export function statusMatchOwner() {
  return api.get('/assets/auto-match/status-owner').then((r) => r.data)
}

export function syncAssets() {
  return api.post('/assets/sync').then((r) => r.data)
}

export function claimAssets(data) {
  return api.post('/assets/claim', data).then((r) => r.data)
}

export function getVMFilters(params) {
  return api.get('/assets/vm-filters', { params }).then((r) => r.data)
}

export function assignAssets(data) {
  return api.post('/assets/assign', data).then((r) => r.data)
}

export function revokeAssets(data) {
  return api.post('/assets/revoke', data).then((r) => r.data)
}

export function resetAllAssets() {
  return api.post('/assets/reset-all').then((r) => r.data)
}
