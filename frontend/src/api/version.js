import api from './index'

export function getVersion() {
  return api.get('/version').then((r) => r.data)
}
